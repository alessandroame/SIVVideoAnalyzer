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

    def update_crop(self, crop_image: Optional[QImage]):
        """Aggiorna il fotogramma ritagliato visualizzato all'interno del riquadro."""
        self._current_crop_image = crop_image
        if crop_image is None or crop_image.isNull():
            self.lbl_viewport.clear()
            self.lbl_viewport.setText(f"{self.title}\nSoggetto non inquadrato")
            self.lbl_viewport.setStyleSheet("background-color: #030712; color: #64748b; font-size: 11px;")
            return

        # Applica eventuale fattore di zoom centrato sul crop
        img = crop_image
        if abs(self.zoom_factor - 1.0) > 0.05:
            zw = max(10, int(img.width() / self.zoom_factor))
            zh = max(10, int(img.height() / self.zoom_factor))
            zx = max(0, (img.width() - zw) // 2)
            zy = max(0, (img.height() - zh) // 2)
            img = img.copy(QRect(zx, zy, zw, zh))

        view_w = max(10, self.lbl_viewport.width())
        view_h = max(10, self.lbl_viewport.height())

        pixmap = QPixmap.fromImage(img).scaled(
            view_w,
            view_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_viewport.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_crop_image and not self._current_crop_image.isNull():
            self.update_crop(self._current_crop_image)

    def _zoom_in(self):
        self._set_zoom(min(3.5, round(self.zoom_factor + 0.25, 2)))

    def _zoom_out(self):
        self._set_zoom(max(1.0, round(self.zoom_factor - 0.25, 2)))

    def _reset_zoom(self):
        self._set_zoom(1.0)

    def _set_zoom(self, val: float):
        self.zoom_factor = val
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

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Ripristina lo zoom o notifica doppio clic."""
        if event.button() == Qt.MouseButton.LeftButton:
            if abs(self.zoom_factor - 1.0) > 0.05:
                self._reset_zoom()
            else:
                self.double_clicked.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
