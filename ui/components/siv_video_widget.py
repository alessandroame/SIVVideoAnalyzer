from typing import Optional, Tuple, List
import cv2
import numpy as np
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QImage, QBrush, QWheelEvent, QMouseEvent
from PyQt6.QtMultimedia import QVideoSink, QVideoFrame


class SIVVideoWidget(QWidget):
    """
    Viewport video nativo ad alte prestazioni basato su QVideoSink.
    Supporta:
    - Rendering video scalato con preservazione dell'aspect ratio (letterbox/pillarbox).
    - Zoom nativo (1.0x - 5.0x) con rotellina del mouse o pulsanti overlay e Pan fluido.
    - Filtro di deinterlacciamento in-memory ultra-rapido (<0.8 ms) con accelerazione vettoriale.
    - Disegno e manipolazione in tempo reale delle bounding box per Vela (arancione) e Pilota (ciano),
      con coordinate proiettate coerentemente nello spazio zoomato.
    - Interazione drag & drop e ridimensionamento tramite maniglie per correggere il tracking.
    - Emissione segnale frame_decoded(QImage) per alimentare i visualizzatori PiP senza duplicare
      la conversione da QVideoFrame.
    """
    escape_pressed = pyqtSignal()
    toggle_fullscreen_requested = pyqtSignal()
    toggle_play_requested = pyqtSignal()
    seek_requested = pyqtSignal(int)
    toggle_tracking_requested = pyqtSignal()
    toggle_boxes_requested = pyqtSignal()
    fullScreenChanged = pyqtSignal(bool)
    frame_decoded = pyqtSignal(QImage)
    arrow_nav_requested = pyqtSignal(int)

    # Segnali per correzione interattiva dei box e keyframe
    box_drag_started = pyqtSignal()
    box_interactively_modified = pyqtSignal(str, list)  # (subject 'pilot'|'wing', [x, y, w, h])
    keyframe_committed = pyqtSignal(str, list)         # (subject 'pilot'|'wing', [x, y, w, h])
    active_subject_changed = pyqtSignal(str)           # (subject 'pilot'|'wing')

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #000000; border-radius: 12px; border: 1px solid #1e293b;")

        self._sink = QVideoSink(self)
        self._sink.videoFrameChanged.connect(self._on_video_frame)

        self._current_frame: Optional[QImage] = None
        self._show_boxes: bool = True
        self._deinterlace_enabled: bool = True
        self._is_fullscreen: bool = False
        self._is_scrubbing: bool = False

        self._pilot_box: Optional[Tuple[int, int, int, int]] = None
        self._wing_box: Optional[Tuple[int, int, int, int]] = None

        # Parametri Pan e Zoom
        self._zoom_factor: float = 1.0
        self._pan_norm_x: float = 0.0
        self._pan_norm_y: float = 0.0
        self._is_panning: bool = False
        self._pan_start_pos: Optional[QPoint] = None
        self._pan_start_offsets: Tuple[float, float] = (0.0, 0.0)

        # Stato di interazione e trascinamento riquadri
        self._hovered_target: Optional[str] = None
        self._hovered_handle: Optional[str] = None
        self._drag_target: Optional[str] = None
        self._drag_handle: Optional[str] = None
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_orig_box: Optional[List[int]] = None
        self._active_target: str = "pilot"

        # Overlay controlli Zoom rapidi
        self._init_zoom_overlay()

    def _init_zoom_overlay(self):
        self.zoom_panel = QWidget(self)
        zp_layout = QHBoxLayout(self.zoom_panel)
        zp_layout.setContentsMargins(6, 4, 6, 4)
        zp_layout.setSpacing(4)
        self.zoom_panel.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 0.85);
                border: 1px solid #334155;
                border-radius: 6px;
            }
        """)

        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_out.setFixedSize(22, 20)
        self.btn_zoom_out.setToolTip("Riduci zoom video principale")
        self.btn_zoom_out.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                padding-bottom: 2px;
            }
            QPushButton:hover { background-color: #334155; color: #ffffff; border-color: #38bdf8; }
        """)
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        zp_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = QPushButton("1.0x")
        self.btn_zoom_reset.setFixedHeight(20)
        self.btn_zoom_reset.setToolTip("Clicca o doppio clic per ripristinare zoom 1.0x")
        self.btn_zoom_reset.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94a3b8;
                border: none;
                font-size: 10px;
                font-weight: 700;
                padding: 0 4px;
            }
            QPushButton:hover { color: #38bdf8; }
        """)
        self.btn_zoom_reset.clicked.connect(self.reset_zoom)
        zp_layout.addWidget(self.btn_zoom_reset)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedSize(22, 20)
        self.btn_zoom_in.setToolTip("Aumenta zoom video principale")
        self.btn_zoom_in.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #334155; color: #ffffff; border-color: #38bdf8; }
        """)
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        zp_layout.addWidget(self.btn_zoom_in)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "zoom_panel"):
            zw = self.zoom_panel.sizeHint().width()
            zh = self.zoom_panel.sizeHint().height()
            self.zoom_panel.setGeometry(self.width() - zw - 14, 14, zw, zh)

    def set_scrubbing(self, scrubbing: bool):
        self._is_scrubbing = scrubbing

    def videoSink(self) -> QVideoSink:
        return self._sink

    def setAspectRatioMode(self, mode):
        pass

    def isFullScreen(self) -> bool:
        return self._is_fullscreen

    def setFullScreen(self, full: bool):
        if full == self._is_fullscreen:
            return
        self._is_fullscreen = full
        if full:
            self.setWindowFlag(Qt.WindowType.Window, True)
            self.showFullScreen()
        else:
            self.setWindowFlag(Qt.WindowType.Window, False)
            self.showNormal()
        self.fullScreenChanged.emit(full)

    def set_bounding_boxes(
        self,
        pilot_box: Optional[Tuple[int, int, int, int]],
        wing_box: Optional[Tuple[int, int, int, int]],
        force_repaint: bool = True
    ):
        self._pilot_box = pilot_box
        self._wing_box = wing_box
        if force_repaint and self._show_boxes:
            self.update()

    def set_show_bounding_boxes(self, show: bool):
        if self._show_boxes != show:
            self._show_boxes = show
            self.update()

    def toggle_bounding_boxes(self) -> bool:
        self.set_show_bounding_boxes(not self._show_boxes)
        return self._show_boxes

    @property
    def show_bounding_boxes(self) -> bool:
        return self._show_boxes

    def set_deinterlace(self, enabled: bool):
        self._deinterlace_enabled = enabled

    def _on_video_frame(self, frame: QVideoFrame):
        if self._is_scrubbing:
            return
        if not frame.isValid():
            return
        qimg = frame.toImage()
        if qimg.isNull():
            return

        if self._deinterlace_enabled:
            qimg = self._deinterlace_image(qimg)

        self._current_frame = qimg
        self.frame_decoded.emit(qimg)
        self.update()

    @staticmethod
    def _deinterlace_image(img: QImage) -> QImage:
        w, h = img.width(), img.height()
        if h <= 2 or w <= 0:
            return img

        formatted = img.convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = formatted.bits()
        ptr.setsize(formatted.sizeInBytes())
        arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4))
        cv2.addWeighted(arr[0:-2:2], 0.5, arr[2::2], 0.5, 0, dst=arr[1:-1:2])
        return formatted

    def display_image(self, qimg: QImage):
        if qimg is None or qimg.isNull():
            return
        if self._deinterlace_enabled:
            qimg = self._deinterlace_image(qimg)
        self._current_frame = qimg
        self.update()

    # =========================================================================
    # METODI PAN & ZOOM
    # =========================================================================
    def zoom_in(self):
        self.set_zoom(min(5.0, round(self._zoom_factor + 0.25, 2)))

    def zoom_out(self):
        self.set_zoom(max(1.0, round(self._zoom_factor - 0.25, 2)))

    def reset_zoom(self):
        self._pan_norm_x = 0.0
        self._pan_norm_y = 0.0
        self.set_zoom(1.0)

    def set_zoom(self, val: float):
        self._zoom_factor = max(1.0, min(5.0, val))
        if self._zoom_factor <= 1.02:
            self._zoom_factor = 1.0
            self._pan_norm_x = 0.0
            self._pan_norm_y = 0.0
            if not self._drag_target:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        elif not self._is_panning and not self._drag_target:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        if hasattr(self, "btn_zoom_reset"):
            self.btn_zoom_reset.setText(f"{self._zoom_factor:.1f}x")
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        elif delta < 0:
            self.zoom_out()
        event.accept()

    def _get_video_layout(self) -> Tuple[Optional[QRect], float, float]:
        """Calcola il rettangolo video scalato a KeepAspectRatio su schermo e i fattori di scala base."""
        if self._current_frame is None or self._current_frame.isNull():
            return None, 1.0, 1.0
        w_w, w_h = self.width(), self.height()
        src_w, src_h = self._current_frame.width(), self._current_frame.height()
        if src_w <= 0 or src_h <= 0 or w_w <= 0 or w_h <= 0:
            return None, 1.0, 1.0

        v_aspect = src_w / src_h
        w_aspect = w_w / w_h

        if w_aspect > v_aspect:
            disp_h = w_h
            disp_w = int(disp_h * v_aspect)
            off_x = (w_w - disp_w) // 2
            off_y = 0
        else:
            disp_w = w_w
            disp_h = int(disp_w / v_aspect)
            off_x = 0
            off_y = (w_h - disp_h) // 2

        scale_x = disp_w / src_w
        scale_y = disp_h / src_h
        return QRect(off_x, off_y, disp_w, disp_h), scale_x, scale_y

    def _get_source_crop(self) -> Tuple[QRect, float, float]:
        """Calcola il ritaglio sorgente nel fotogramma video (in coordinate native) per zoom e pan."""
        if self._current_frame is None or self._current_frame.isNull():
            return QRect(0, 0, 1920, 1080), 1920.0, 1080.0
        src_w = float(self._current_frame.width())
        src_h = float(self._current_frame.height())

        if self._zoom_factor <= 1.02:
            return QRect(0, 0, int(src_w), int(src_h)), src_w, src_h

        cw = max(10.0, src_w / self._zoom_factor)
        ch = max(10.0, src_h / self._zoom_factor)

        max_slack_x = max(0.0, (src_w - cw) / 2.0)
        max_slack_y = max(0.0, (src_h - ch) / 2.0)

        cx = (src_w / 2.0) + (self._pan_norm_x * max_slack_x)
        cy = (src_h / 2.0) + (self._pan_norm_y * max_slack_y)

        x0 = max(0.0, min(src_w - cw, cx - cw / 2.0))
        y0 = max(0.0, min(src_h - ch, cy - ch / 2.0))

        crop_rect = QRect(int(round(x0)), int(round(y0)), int(round(cw)), int(round(ch)))
        return crop_rect, cw, ch

    def _map_video_box_to_screen(self, box: Tuple[int, int, int, int]) -> Optional[QRect]:
        rect, _, _ = self._get_video_layout()
        if not rect:
            return None
        crop_rect, cw, ch = self._get_source_crop()
        bx, by, bw, bh = box

        sx = rect.width() / max(1.0, cw)
        sy = rect.height() / max(1.0, ch)

        screen_x = rect.x() + int(round((bx - crop_rect.x()) * sx))
        screen_y = rect.y() + int(round((by - crop_rect.y()) * sy))
        screen_w = int(round(bw * sx))
        screen_h = int(round(bh * sy))
        return QRect(screen_x, screen_y, screen_w, screen_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Sfondo nero per le bande letterbox/pillarbox
        painter.fillRect(self.rect(), QColor("#000000"))

        if self._current_frame is None or self._current_frame.isNull():
            painter.end()
            return

        target_rect, _, _ = self._get_video_layout()
        if target_rect is None:
            painter.end()
            return

        source_crop, _, _ = self._get_source_crop()
        painter.drawImage(target_rect, self._current_frame, source_crop)

        # Disegno dei riquadri di Pilota e Vela
        if self._show_boxes and (self._wing_box or self._pilot_box):
            painter.save()
            painter.setClipRect(target_rect)
            font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            painter.setFont(font)

            # 1. Riquadro VELA (Arancione #f59e0b)
            if self._wing_box:
                rw = self._map_video_box_to_screen(self._wing_box)
                if rw:
                    is_active = (self._hovered_target == "wing" or self._drag_target == "wing")
                    self._draw_box_with_handles(painter, rw, "VELA", "#f59e0b", is_active)

            # 2. Riquadro CORPO PILOTA (Ciano #06b6d4)
            if self._pilot_box:
                rp = self._map_video_box_to_screen(self._pilot_box)
                if rp:
                    is_active = (self._hovered_target == "pilot" or self._drag_target == "pilot")
                    self._draw_box_with_handles(painter, rp, "PILOTA", "#06b6d4", is_active)

            painter.restore()

        painter.end()

    def _draw_box_with_handles(self, painter: QPainter, r: QRect, label: str, color_hex: str, is_active: bool):
        pen = QPen(QColor(color_hex), 3.0 if is_active else 2.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)

        if is_active:
            hs = 8
            painter.setPen(QPen(QColor("#0f172a"), 1.5))
            painter.setBrush(QBrush(QColor(color_hex)))
            corners = [(r.left(), r.top()), (r.right(), r.top()), (r.left(), r.bottom()), (r.right(), r.bottom())]
            for cx, cy in corners:
                painter.drawRect(QRect(cx - hs // 2, cy - hs // 2, hs, hs))

        tx = r.x()
        ty = r.y() - 5 if r.y() >= 20 else r.y() + 16
        painter.setPen(QColor(0, 0, 0, 200))
        painter.drawText(tx + 1, ty + 1, label)
        painter.setPen(QColor(color_hex))
        painter.drawText(tx, ty, label)

    def _hit_test_boxes(self, pos: QPoint) -> Tuple[Optional[str], Optional[str]]:
        if not self._show_boxes:
            return None, None
        for subject, box in [("pilot", self._pilot_box), ("wing", self._wing_box)]:
            if not box:
                continue
            r = self._map_video_box_to_screen(box)
            if not r or not r.isValid():
                continue
            hs = 12
            if abs(pos.x() - r.left()) <= hs and abs(pos.y() - r.top()) <= hs:
                return subject, "tl"
            if abs(pos.x() - r.right()) <= hs and abs(pos.y() - r.top()) <= hs:
                return subject, "tr"
            if abs(pos.x() - r.left()) <= hs and abs(pos.y() - r.bottom()) <= hs:
                return subject, "bl"
            if abs(pos.x() - r.right()) <= hs and abs(pos.y() - r.bottom()) <= hs:
                return subject, "br"
            if r.contains(pos):
                return subject, "move"
        return None, None

    def mousePressEvent(self, event: QMouseEvent):
        self.setFocus()

        # Pan con tasto centrale o destro ovunque
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            if self._zoom_factor > 1.02:
                self._is_panning = True
                self._pan_start_pos = event.pos()
                self._pan_start_offsets = (self._pan_norm_x, self._pan_norm_y)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

        # Clic sinistro su un box di tracking per spostarlo / ridimensionarlo
        if event.button() == Qt.MouseButton.LeftButton and self._show_boxes:
            subj, handle = self._hit_test_boxes(event.pos())
            if subj:
                self._drag_target = subj
                self._drag_handle = handle
                self._drag_start_pos = event.pos()
                orig = self._pilot_box if subj == "pilot" else self._wing_box
                self._drag_orig_box = list(orig) if orig else None
                self._active_target = subj
                self.active_subject_changed.emit(subj)
                self.box_drag_started.emit()
                self.update()
                event.accept()
                return

        # Clic sinistro fuori dai box quando il video è zoomato attiva il Pan
        if event.button() == Qt.MouseButton.LeftButton and self._zoom_factor > 1.02:
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self._pan_start_offsets = (self._pan_norm_x, self._pan_norm_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # 1. Spostamento / Ridimensionamento Box di Tracking
        if self._drag_target and self._drag_orig_box and self._drag_start_pos:
            rect, _, _ = self._get_video_layout()
            crop_rect, cw, ch = self._get_source_crop()
            if rect and cw > 0 and ch > 0:
                sx = rect.width() / cw
                sy = rect.height() / ch
                dx_vid = (event.pos().x() - self._drag_start_pos.x()) / sx
                dy_vid = (event.pos().y() - self._drag_start_pos.y()) / sy
                ox, oy, ow, oh = self._drag_orig_box
                src_w = self._current_frame.width() if self._current_frame else 1920
                src_h = self._current_frame.height() if self._current_frame else 1080

                if self._drag_handle == "move":
                    nx = max(0, min(src_w - ow, int(round(ox + dx_vid))))
                    ny = max(0, min(src_h - oh, int(round(oy + dy_vid))))
                    nw, nh = ow, oh
                elif self._drag_handle == "br":
                    nw = max(20, min(src_w - ox, int(round(ow + dx_vid))))
                    nh = max(20, min(src_h - oy, int(round(oh + dy_vid))))
                    nx, ny = ox, oy
                elif self._drag_handle == "tl":
                    nx = max(0, min(ox + ow - 20, int(round(ox + dx_vid))))
                    ny = max(0, min(oy + oh - 20, int(round(oy + dy_vid))))
                    nw = max(20, ox + ow - nx)
                    nh = max(20, oy + oh - ny)
                elif self._drag_handle == "tr":
                    ny = max(0, min(oy + oh - 20, int(round(oy + dy_vid))))
                    nw = max(20, min(src_w - ox, int(round(ow + dx_vid))))
                    nh = max(20, oy + oh - ny)
                    nx = ox
                elif self._drag_handle == "bl":
                    nx = max(0, min(ox + ow - 20, int(round(ox + dx_vid))))
                    nw = max(20, ox + ow - nx)
                    nh = max(20, min(src_h - oy, int(round(oh + dy_vid))))
                    ny = oy
                else:
                    nx, ny, nw, nh = ox, oy, ow, oh

                new_box = (nx, ny, nw, nh)
                if self._drag_target == "pilot":
                    self._pilot_box = new_box
                else:
                    self._wing_box = new_box

                self.box_interactively_modified.emit(self._drag_target, list(new_box))
                self.update()
                event.accept()
                return

        # 2. Pan del video quando zoomato
        if self._is_panning and self._pan_start_pos and self._zoom_factor > 1.02:
            rect, _, _ = self._get_video_layout()
            if rect and self._current_frame:
                src_w = float(self._current_frame.width())
                src_h = float(self._current_frame.height())
                cw = max(10.0, src_w / self._zoom_factor)
                ch = max(10.0, src_h / self._zoom_factor)
                max_slack_x = max(1.0, (src_w - cw) / 2.0)
                max_slack_y = max(1.0, (src_h - ch) / 2.0)

                delta = event.pos() - self._pan_start_pos
                delta_norm_x = -(delta.x() * (cw / max(1.0, float(rect.width())))) / max_slack_x
                delta_norm_y = -(delta.y() * (ch / max(1.0, float(rect.height())))) / max_slack_y

                self._pan_norm_x = max(-1.0, min(1.0, self._pan_start_offsets[0] + delta_norm_x))
                self._pan_norm_y = max(-1.0, min(1.0, self._pan_start_offsets[1] + delta_norm_y))
                self.update()
                event.accept()
                return

        # 3. Hovering e forme del cursore
        subj, handle = self._hit_test_boxes(event.pos())
        if subj != self._hovered_target or handle != self._hovered_handle:
            self._hovered_target = subj
            self._hovered_handle = handle
            self.update()

        if handle in ("tl", "br"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in ("tr", "bl"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif handle == "move":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif self._zoom_factor > 1.02:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._is_panning:
            self._is_panning = False
            if self._zoom_factor > 1.02:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._drag_target:
            curr_box = self._pilot_box if self._drag_target == "pilot" else self._wing_box
            if curr_box:
                self.keyframe_committed.emit(self._drag_target, list(curr_box))
            self._drag_target = None
            self._drag_handle = None
            self._drag_start_pos = None
            self._drag_orig_box = None
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._zoom_factor > 1.05 or abs(self._pan_norm_x) > 0.01 or abs(self._pan_norm_y) > 0.01:
                self.reset_zoom()
                event.accept()
                return
            else:
                self.setFullScreen(not self.isFullScreen())
                self.toggle_fullscreen_requested.emit()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event):
        if self._hovered_target is not None or self._hovered_handle is not None:
            self._hovered_target = None
            self._hovered_handle = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.setFullScreen(False)
            self.escape_pressed.emit()
            event.accept()
        elif key == Qt.Key.Key_F:
            self.setFullScreen(not self.isFullScreen())
            self.toggle_fullscreen_requested.emit()
            event.accept()
        elif key == Qt.Key.Key_T:
            self.toggle_tracking_requested.emit()
            event.accept()
        elif key == Qt.Key.Key_B:
            self.toggle_bounding_boxes()
            self.toggle_boxes_requested.emit()
            event.accept()
        elif key == Qt.Key.Key_Space:
            self.toggle_play_requested.emit()
            event.accept()
        elif key == Qt.Key.Key_Left:
            self.arrow_nav_requested.emit(-1)
            event.accept()
        elif key == Qt.Key.Key_Right:
            self.arrow_nav_requested.emit(1)
            event.accept()
        else:
            super().keyPressEvent(event)
