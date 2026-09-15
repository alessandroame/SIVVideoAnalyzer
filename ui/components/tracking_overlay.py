from typing import Optional, List, Tuple
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QImage
from PyQt6.QtMultimedia import QVideoFrame

from ui.components.tracking_pip_widget import TrackingPipWidget
from core.sidecar_manager import SidecarData


class TrackingOverlayWidget(QWidget):
    """
    Overlay trasparente sovrapposto al player video:
    - Alloggia i due riquadri PiP (Vela e Pilota)
    - Disegna i bounding box coordinati sul video master
    - Intercetta i frame video da QVideoSink ed estrae i crop in tempo reale
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background-color: transparent;")

        self.current_sidecar: Optional[SidecarData] = None
        self.is_tracking_visible = True
        self.show_bounding_boxes = True

        self._curr_pilot_box: Optional[List[int]] = None
        self._curr_wing_box: Optional[List[int]] = None
        self._video_source_size = (1920, 1080)

        # Istanzia i due riquadri
        self.pip_wing = TrackingPipWidget(
            title="🟠 VELA & ASSETTO",
            accent_color="#f59e0b",
            parent=self
        )
        self.pip_pilot = TrackingPipWidget(
            title="🔵 CORPO PILOTA",
            accent_color="#38bdf8",
            parent=self
        )

        self._user_dragged = False
        self._reposition_pips()

    def set_sidecar(self, sidecar: Optional[SidecarData]):
        """Assegna il sidecar del video attivo."""
        self.current_sidecar = sidecar
        if sidecar and sidecar.tracking:
            vw = sidecar.tracking.get("video_width", 1920)
            vh = sidecar.tracking.get("video_height", 1080)
            self._video_source_size = (vw, vh)

    def toggle_tracking(self) -> bool:
        """Alterna visibilità dei riquadri di tracking e ritorna il nuovo stato."""
        self.is_tracking_visible = not self.is_tracking_visible
        self.pip_wing.setVisible(self.is_tracking_visible)
        self.pip_pilot.setVisible(self.is_tracking_visible)
        self.update()
        return self.is_tracking_visible

    def set_tracking_visible(self, visible: bool):
        self.is_tracking_visible = visible
        self.pip_wing.setVisible(visible)
        self.pip_pilot.setVisible(visible)
        self.update()

    def handle_video_frame(self, frame: QVideoFrame, curr_time_sec: float):
        """
        Processa il frame video nativo:
        estrae i due crop e comanda l'aggiornamento dei riquadri e dei bounding box.
        """
        if not self.is_tracking_visible or not self.current_sidecar or not self.current_sidecar.has_tracking():
            self._curr_pilot_box = None
            self._curr_wing_box = None
            self.update()
            return

        p_box, w_box = self.current_sidecar.get_tracking_boxes_at(curr_time_sec)
        self._curr_pilot_box = p_box
        self._curr_wing_box = w_box

        if not frame.isValid():
            return

        qimg = frame.toImage()
        if qimg.isNull():
            return

        self._video_source_size = (qimg.width(), qimg.height())

        # Ritaglio Pilota
        if p_box:
            px, py, pw, ph = p_box
            crop_rect = QRect(px, py, pw, ph).intersected(QRect(0, 0, qimg.width(), qimg.height()))
            if not crop_rect.isEmpty():
                self.pip_pilot.update_crop(qimg.copy(crop_rect))
            else:
                self.pip_pilot.update_crop(None)
        else:
            self.pip_pilot.update_crop(None)

        # Ritaglio Vela
        if w_box:
            wx, wy, ww, wh = w_box
            crop_rect = QRect(wx, wy, ww, wh).intersected(QRect(0, 0, qimg.width(), qimg.height()))
            if not crop_rect.isEmpty():
                self.pip_wing.update_crop(qimg.copy(crop_rect))
            else:
                self.pip_wing.update_crop(None)
        else:
            self.pip_wing.update_crop(None)

        self.update()

    def paintEvent(self, event):
        """Disegna le coordinate delle bounding box sul video principale."""
        if not self.is_tracking_visible or not self.show_bounding_boxes:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        src_w, src_h = self._video_source_size
        if src_w <= 0 or src_h <= 0:
            return

        scale_x = self.width() / src_w
        scale_y = self.height() / src_h

        # Disegna box Vela
        if self._curr_wing_box:
            wx, wy, ww, wh = self._curr_wing_box
            rect_w = QRect(
                int(wx * scale_x),
                int(wy * scale_y),
                int(ww * scale_x),
                int(wh * scale_y)
            )
            pen_wing = QPen(QColor("#f59e0b"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen_wing)
            painter.drawRoundedRect(rect_w, 6, 6)

            # Badge etichetta
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.fillRect(rect_w.x(), max(0, rect_w.y() - 18), 50, 16, QColor(11, 17, 30, 200))
            painter.setPen(QColor("#f59e0b"))
            painter.drawText(rect_w.x() + 4, max(12, rect_w.y() - 5), "VELA")

        # Disegna box Pilota
        if self._curr_pilot_box:
            px, py, pw, ph = self._curr_pilot_box
            rect_p = QRect(
                int(px * scale_x),
                int(py * scale_y),
                int(pw * scale_x),
                int(ph * scale_y)
            )
            pen_pilot = QPen(QColor("#38bdf8"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen_pilot)
            painter.drawRoundedRect(rect_p, 6, 6)

            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.fillRect(rect_p.x(), max(0, rect_p.y() - 18), 60, 16, QColor(11, 17, 30, 200))
            painter.setPen(QColor("#38bdf8"))
            painter.drawText(rect_p.x() + 4, max(12, rect_p.y() - 5), "PILOTA")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_pips()

    def _reposition_pips(self):
        """Posiziona i riquadri impilati in alto a destra."""
        if not self._user_dragged:
            right_margin = 16
            top_margin = 16
            spacing = 10
            pip_w = self.pip_wing.width()
            pip_h = self.pip_wing.height()

            pos_x = max(0, self.width() - pip_w - right_margin)
            self.pip_wing.move(pos_x, top_margin)
            self.pip_pilot.move(pos_x, top_margin + pip_h + spacing)
