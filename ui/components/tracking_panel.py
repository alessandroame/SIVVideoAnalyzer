from typing import Optional, List, Tuple
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QImage
from PyQt6.QtMultimedia import QVideoFrame

from ui.components.tracking_pip_widget import TrackingPipWidget
from core.sidecar_manager import SidecarData


class TrackingPanelWidget(QFrame):
    """
    Pannello laterale dedicato al debriefing video contenente i due visualizzatori
    sincronizzati e zoomati:
    1. '🟠 VELA & ASSETTO' (beccheggio, rollio, chiusure, configurazione semiali)
    2. '🔵 CORPO PILOTA' (spostamento baricentro, azione sui comandi/freni, tensione imbrago)
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_sidecar: Optional[SidecarData] = None
        self._init_ui()

    def _init_ui(self):
        self.setObjectName("trackingPanel")
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("""
            QFrame#trackingPanel {
                background-color: #0b111e;
                border: 1px solid #1e293b;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header del Pannello
        header = QHBoxLayout()
        header.setContentsMargins(2, 2, 2, 2)

        lbl_title = QLabel("TRACCIAMENTO SOGGETTI")
        lbl_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #38bdf8; letter-spacing: 0.5px;")
        header.addWidget(lbl_title)

        header.addStretch()

        self.lbl_status = QLabel("⚪ In attesa")
        self.lbl_status.setStyleSheet("font-size: 10px; font-weight: 600; color: #94a3b8;")
        header.addWidget(self.lbl_status)

        layout.addLayout(header)

        # Riquadro 1: Vela & Assetto
        self.pip_wing = TrackingPipWidget(
            title="🟠 VELA & ASSETTO",
            accent_color="#f59e0b",
            parent=self
        )
        layout.addWidget(self.pip_wing, stretch=1)

        # Riquadro 2: Corpo Pilota
        self.pip_pilot = TrackingPipWidget(
            title="🔵 CORPO PILOTA",
            accent_color="#38bdf8",
            parent=self
        )
        layout.addWidget(self.pip_pilot, stretch=1)

    def set_sidecar(self, sidecar: Optional[SidecarData]):
        """Assegna il sidecar del volo corrente e aggiorna lo stato visivo."""
        self.current_sidecar = sidecar
        if not sidecar:
            self.lbl_status.setText("⚪ Nessun video")
            self.lbl_status.setStyleSheet("font-size: 10px; font-weight: 600; color: #94a3b8;")
            self.set_status_all("Nessun video caricato")
        elif sidecar.has_tracking():
            self.lbl_status.setText("🟢 Sincronizzato")
            self.lbl_status.setStyleSheet("font-size: 10px; font-weight: 700; color: #10b981;")
            self.pip_wing.set_status_text("🟠 VELA & ASSETTO\nPronto alla riproduzione")
            self.pip_pilot.set_status_text("🔵 CORPO PILOTA\nPronto alla riproduzione")
        else:
            self.lbl_status.setText("⏳ In calcolo...")
            self.lbl_status.setStyleSheet("font-size: 10px; font-weight: 600; color: #fbbf24;")
            self.set_status_all("Calcolo coordinate in corso...")

    def set_status_all(self, text: str):
        """Imposta il messaggio informativo su entrambi i riquadri."""
        self.pip_wing.set_status_text(f"🟠 VELA & ASSETTO\n{text}")
        self.pip_pilot.set_status_text(f"🔵 CORPO PILOTA\n{text}")

    def handle_video_frame(self, frame: QVideoFrame, curr_time_sec: float):
        """
        Intercetta il frame video nativo da QVideoSink,
        estrae i crop corrispondenti a Pilota e Vela in base alla traiettoria
        stabilizzata del sidecar e comanda l'aggiornamento dei due visualizzatori.
        """
        if not self.isVisible() or not self.current_sidecar or not self.current_sidecar.has_tracking():
            return

        p_box, w_box = self.current_sidecar.get_tracking_boxes_at(curr_time_sec)

        if not frame.isValid():
            return

        qimg = frame.toImage()
        if qimg.isNull():
            return

        img_w, img_h = qimg.width(), qimg.height()

        # Ritaglio Vela & Assetto
        if w_box:
            wx, wy, ww, wh = w_box
            crop_rect_w = QRect(int(wx), int(wy), int(ww), int(wh)).intersected(QRect(0, 0, img_w, img_h))
            if not crop_rect_w.isEmpty():
                self.pip_wing.update_crop(qimg.copy(crop_rect_w))
            else:
                self.pip_wing.update_crop(None)
        else:
            self.pip_wing.update_crop(None)

        # Ritaglio Corpo Pilota
        if p_box:
            px, py, pw, ph = p_box
            crop_rect_p = QRect(int(px), int(py), int(pw), int(ph)).intersected(QRect(0, 0, img_w, img_h))
            if not crop_rect_p.isEmpty():
                self.pip_pilot.update_crop(qimg.copy(crop_rect_p))
            else:
                self.pip_pilot.update_crop(None)
        else:
            self.pip_pilot.update_crop(None)
