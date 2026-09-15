from typing import Optional
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QRect
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QWheelEvent, QMouseEvent


class TrackingPipWidget(QFrame):
    """
    Riquadro Picture-in-Picture (PiP) fluttuante per il tracciamento zoomato.
    Supporta:
    - Bordo cromatico tematico (Ciano per Pilota, Arancio per Vela)
    - Zoom dinamico regolabile con rotellina del mouse (1.0x - 3.0x)
    - Trascinamento (drag & drop) per riposizionamento libero sullo schermo
    - Doppio click per ingrandimento o focus
    """
    double_clicked = pyqtSignal()
    close_requested = pyqtSignal()

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
        self._dragging = False
        self._drag_start_pos = QPoint()

        self._current_crop_image: Optional[QImage] = None

        self._init_ui()

    def _init_ui(self):
        self.setObjectName("trackingPip")
        self.setFixedSize(260, 180)
        self.setStyleSheet(f"""
            QFrame#trackingPip {{
                background-color: rgba(11, 17, 30, 0.92);
                border: 2px solid {self.accent_color};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header Bar
        header = QHBoxLayout()
        header.setContentsMargins(4, 2, 4, 2)

        self.lbl_title = QLabel(self.title)
        self.lbl_title.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 800;
            color: {self.accent_color};
            letter-spacing: 0.5px;
        """)
        header.addWidget(self.lbl_title)

        header.addStretch()

        self.lbl_zoom = QLabel("1.0x")
        self.lbl_zoom.setStyleSheet("font-size: 10px; font-weight: 600; color: #94a3b8;")
        header.addWidget(self.lbl_zoom)

        layout.addLayout(header)

        # Area di rendering del Crop
        self.lbl_viewport = QLabel()
        self.lbl_viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_viewport.setStyleSheet("""
            background-color: #000000;
            border-radius: 6px;
        """)
        self.lbl_viewport.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.lbl_viewport, stretch=1)

    def update_crop(self, crop_image: Optional[QImage]):
        """Aggiorna il fotogramma ritagliato visualizzato all'interno del riquadro."""
        self._current_crop_image = crop_image
        if crop_image is None or crop_image.isNull():
            self.lbl_viewport.clear()
            self.lbl_viewport.setText("Soggetto non inquadrato")
            self.lbl_viewport.setStyleSheet("background-color: #000000; color: #64748b; font-size: 11px;")
            return

        # Applica eventuale fattore di zoom centrato sul crop
        img = crop_image
        if abs(self.zoom_factor - 1.0) > 0.05:
            zw = int(img.width() / self.zoom_factor)
            zh = int(img.height() / self.zoom_factor)
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

    def wheelEvent(self, event: QWheelEvent):
        """Regola il livello di zoom con la rotellina del mouse."""
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_factor = min(3.0, round(self.zoom_factor + 0.2, 1))
        elif delta < 0:
            self.zoom_factor = max(1.0, round(self.zoom_factor - 0.2, 1))

        self.lbl_zoom.setText(f"{self.zoom_factor:.1f}x")
        if self._current_crop_image:
            self.update_crop(self._current_crop_image)
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Espande o ripristina la vista su doppio clic."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """Avvia il trascinamento del riquadro."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Trascina il riquadro mantenendolo all'interno dei limiti del contenitore genitore."""
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            if self.parentWidget():
                new_pos = event.globalPosition().toPoint() - self._drag_start_pos
                max_x = max(0, self.parentWidget().width() - self.width())
                max_y = max(0, self.parentWidget().height() - self.height())
                clamped_x = max(0, min(new_pos.x(), max_x))
                clamped_y = max(0, min(new_pos.y(), max_y))
                self.move(clamped_x, clamped_y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False
        super().mouseReleaseEvent(event)
