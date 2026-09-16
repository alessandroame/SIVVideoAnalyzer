from typing import Optional
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QRect
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QWheelEvent, QMouseEvent


class TrackingPipWidget(QFrame):
    """
    Pannello visualizzatore per il tracciamento zoomato di Pilota o Vela.
    Supporta:
    - Bordo tematico ad alto contrasto (Ciano per Pilota, Arancio per Vela)
    - Zoom regolabile da 1.0x a 3.5x con pulsanti (+ / - / Reset) o rotellina mouse
    - Ridimensionamento dinamico proporzionale al contenitore
    - Visualizzazione nitida e fluida dei crop video sincronizzati
    """
    double_clicked = pyqtSignal()

    def __init__(
        self,
        title: str = "PILOTA",
        accent_color: str = "#38bdf8",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.title = title
        self.accent_color = accent_color
        self.zoom_factor = 1.0
        self.pan_norm_x = 0.0
        self.pan_norm_y = 0.0
        self._is_panning = False
        self._drag_start_pos = QPoint()
        self._drag_start_pan = (0.0, 0.0)
        self._current_crop_image: Optional[QImage] = None

        self._init_ui()

    def _init_ui(self):
        self.setObjectName("trackingPip")
        self.setMinimumSize(220, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"""
            QFrame#trackingPip {{
                background-color: #080e1a;
                border: 2px solid {self.accent_color};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setSpacing(6)

        # Header Bar
        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 2, 0)
        header.setSpacing(6)

        self.lbl_title = QLabel(self.title)
        self.lbl_title.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 800;
            color: {self.accent_color};
            letter-spacing: 0.5px;
        """)
        header.addWidget(self.lbl_title)

        header.addStretch()

        # Controlli di zoom rapidi
        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_out.setFixedSize(22, 20)
        self.btn_zoom_out.setToolTip("Riduci zoom")
        self.btn_zoom_out.setStyleSheet("""
            QPushButton {
                background-color: #131b2e;
                color: #94a3b8;
                border: 1px solid #23314f;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                padding-bottom: 2px;
            }
            QPushButton:hover { background-color: #1c263d; color: #ffffff; border-color: #38bdf8; }
        """)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        header.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = QPushButton("1.0x")
        self.btn_zoom_reset.setFixedHeight(20)
        self.btn_zoom_reset.setToolTip("Clicca per ripristinare zoom 1.0x")
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
        self.btn_zoom_reset.clicked.connect(self._reset_zoom)
        header.addWidget(self.btn_zoom_reset)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setFixedSize(22, 20)
        self.btn_zoom_in.setToolTip("Aumenta zoom")
        self.btn_zoom_in.setStyleSheet("""
            QPushButton {
                background-color: #131b2e;
                color: #94a3b8;
                border: 1px solid #23314f;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #1c263d; color: #ffffff; border-color: #38bdf8; }
        """)
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        header.addWidget(self.btn_zoom_in)

        layout.addLayout(header)

        # Area di rendering del Crop
        self.lbl_viewport = QLabel(f"{self.title}\nIn attesa di tracciamento...")
        self.lbl_viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_viewport.setStyleSheet("""
            background-color: #030712;
            color: #64748b;
            font-size: 11px;
            font-weight: 600;
            border-radius: 6px;
        """)
        self.lbl_viewport.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.lbl_viewport.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.lbl_viewport, stretch=1)

    def set_status_text(self, text: str):
        """Imposta un messaggio di stato visibile nel riquadro prima o durante il tracciamento."""
        self._current_crop_image = None
        self.lbl_viewport.clear()
        self.lbl_viewport.setText(text)
        self.lbl_viewport.setStyleSheet("""
            background-color: #030712;
            color: #38bdf8;
            font-size: 11px;
            font-weight: 600;
            border-radius: 6px;
        """)

    def viewport_aspect_ratio(self) -> float:
        """Restituisce il rapporto d'aspetto (larghezza / altezza) del viewport attuale per la vista panoramica."""
        vw = self.lbl_viewport.width()
        vh = self.lbl_viewport.height()
        if vw > 20 and vh > 20:
            return max(1.33, min(2.5, vw / vh))
        return 16.0 / 9.0

    def update_crop(self, crop_image: Optional[QImage]):
        """Aggiorna il fotogramma ritagliato visualizzato all'interno del riquadro."""
        self._current_crop_image = crop_image
        if crop_image is None or crop_image.isNull():
            self.lbl_viewport.clear()
            self.lbl_viewport.setText(f"{self.title}\nSoggetto non inquadrato")
            self.lbl_viewport.setStyleSheet("background-color: #030712; color: #64748b; font-size: 11px;")
            return

        # Applica eventuale fattore di zoom e pan sul crop
        img = crop_image
        if abs(self.zoom_factor - 1.0) > 0.05:
            zw = max(10, int(img.width() / self.zoom_factor))
            zh = max(10, int(img.height() / self.zoom_factor))
            max_slack_x = max(0, (img.width() - zw) // 2)
            max_slack_y = max(0, (img.height() - zh) // 2)

            center_x = (img.width() - zw) // 2
            center_y = (img.height() - zh) // 2

            zx = int(center_x + self.pan_norm_x * max_slack_x)
            zy = int(center_y + self.pan_norm_y * max_slack_y)

            zx = max(0, min(img.width() - zw, zx))
            zy = max(0, min(img.height() - zh, zy))

            img = img.copy(QRect(zx, zy, zw, zh))

        view_w = max(10, self.lbl_viewport.width())
        view_h = max(10, self.lbl_viewport.height())

        pixmap = QPixmap.fromImage(img).scaled(
            view_w,
            view_h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_viewport.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_crop_image and not self._current_crop_image.isNull():
            self.update_crop(self._current_crop_image)

    def _zoom_in(self):
        self._set_zoom(min(5.0, round(self.zoom_factor + 0.25, 2)))

    def _zoom_out(self):
        self._set_zoom(max(1.0, round(self.zoom_factor - 0.25, 2)))

    def _reset_zoom(self):
        self.pan_norm_x = 0.0
        self.pan_norm_y = 0.0
        self._set_zoom(1.0)

    def _set_zoom(self, val: float):
        self.zoom_factor = val
        if self.zoom_factor <= 1.05:
            self.pan_norm_x = 0.0
            self.pan_norm_y = 0.0
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        self.btn_zoom_reset.setText(f"{self.zoom_factor:.1f}x")
        if self._current_crop_image:
            self.update_crop(self._current_crop_image)

    def wheelEvent(self, event: QWheelEvent):
        """Regola il livello di zoom con la rotellina del mouse."""
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom_in()
        elif delta < 0:
            self._zoom_out()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        """Inizia l'operazione di Pan (trascinamento) se il riquadro è zoomato."""
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            if self.zoom_factor > 1.05:
                self._is_panning = True
                self._drag_start_pos = event.pos()
                self._drag_start_pan = (self.pan_norm_x, self.pan_norm_y)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Trascina la visuale (Pan) proporzionalmente al movimento del mouse."""
        if self._is_panning and self._current_crop_image and not self._current_crop_image.isNull():
            delta = event.pos() - self._drag_start_pos
            img = self._current_crop_image
            zw = max(10, int(img.width() / self.zoom_factor))
            zh = max(10, int(img.height() / self.zoom_factor))
            max_slack_x = max(1, (img.width() - zw) // 2)
            max_slack_y = max(1, (img.height() - zh) // 2)

            view_w = max(10, self.lbl_viewport.width())
            view_h = max(10, self.lbl_viewport.height())

            delta_norm_x = -(delta.x() * (zw / view_w)) / max_slack_x
            delta_norm_y = -(delta.y() * (zh / view_h)) / max_slack_y

            self.pan_norm_x = max(-1.0, min(1.0, self._drag_start_pan[0] + delta_norm_x))
            self.pan_norm_y = max(-1.0, min(1.0, self._drag_start_pan[1] + delta_norm_y))

            self.update_crop(self._current_crop_image)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Termina il trascinamento e ripristina il cursore."""
        if self._is_panning:
            self._is_panning = False
            if self.zoom_factor > 1.05:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Ripristina lo zoom e il pan o notifica doppio clic."""
        if event.button() == Qt.MouseButton.LeftButton:
            if abs(self.zoom_factor - 1.0) > 0.05 or abs(self.pan_norm_x) > 0.01 or abs(self.pan_norm_y) > 0.01:
                self._reset_zoom()
            else:
                self.double_clicked.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
