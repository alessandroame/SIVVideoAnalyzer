import time
from typing import Optional, List, Tuple
import cv2
import numpy as np
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
        self._last_update_time: float = 0.0
        self._smooth_crop_w: Optional[Tuple[float, float, float, float]] = None
        self._smooth_crop_p: Optional[Tuple[float, float, float, float]] = None
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
        self._smooth_crop_w = None
        self._smooth_crop_p = None
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
        """Intercetta il frame video nativo da QVideoSink e aggiorna i crop."""
        if not frame.isValid():
            return
        qimg = frame.toImage()
        self.handle_qimage_frame(qimg, curr_time_sec)

    def _apply_pip_smoothing(
        self,
        target_rect: QRect,
        subject: str,
        img_w: int,
        img_h: int,
        force: bool = False
    ) -> QRect:
        """Filtro cinematico fluido (smooth camera gimbal) per il PiP per eliminare ogni vibrazione."""
        if target_rect.isEmpty():
            return target_rect

        t_box = (
            float(target_rect.x()),
            float(target_rect.y()),
            float(target_rect.width()),
            float(target_rect.height())
        )
        last_box = self._smooth_crop_w if subject == "wing" else self._smooth_crop_p

        if force or last_box is None:
            if subject == "wing":
                self._smooth_crop_w = t_box
            else:
                self._smooth_crop_p = t_box
            return target_rect

        # Smoothing fluido esponenziale con alpha = 0.30
        alpha = 0.30
        new_box = [
            last_box[i] * (1.0 - alpha) + t_box[i] * alpha
            for i in range(4)
        ]

        if subject == "wing":
            self._smooth_crop_w = tuple(new_box)
        else:
            self._smooth_crop_p = tuple(new_box)

        rx = max(0, min(img_w - 1, int(round(new_box[0]))))
        ry = max(0, min(img_h - 1, int(round(new_box[1]))))
        rw = min(img_w - rx, max(1, int(round(new_box[2]))))
        rh = min(img_h - ry, max(1, int(round(new_box[3]))))

        return QRect(rx, ry, rw, rh)

    def handle_qimage_frame(
        self,
        qimg: QImage,
        curr_time_sec: float,
        force: bool = False,
        override_boxes: Optional[dict] = None
    ):
        """Estrae i crop corrispondenti a Pilota e Vela a partire da un QImage
        e comanda l'aggiornamento dei due visualizzatori.
        Durante il playback continuo (force=False), limita gli aggiornamenti a max 25 fps (~40 ms)
        per preservare il 100% della fluidità del video principale.
        Supporta override_boxes={'pilot': [x, y, w, h]} per aggiornamento live immediato
        durante il trascinamento o ridimensionamento dei riquadri sul video principale.
        """
        if not self.isVisible():
            return

        if qimg is None or qimg.isNull():
            return

        now = time.perf_counter()
        if not force:
            if (now - self._last_update_time) < 0.040:
                return
            self._last_update_time = now
        else:
            self._last_update_time = now

        p_box, w_box = None, None
        if self.current_sidecar and self.current_sidecar.has_tracking():
            p_box, w_box = self.current_sidecar.get_tracking_boxes_at(curr_time_sec)

        if override_boxes:
            if "pilot" in override_boxes:
                p_box = tuple(override_boxes["pilot"])
            if "wing" in override_boxes:
                w_box = tuple(override_boxes["wing"])

        if not p_box and not w_box:
            return

        img_w, img_h = qimg.width(), qimg.height()

        # Ritaglio Vela & Assetto (Vista Larga Panoramica con camera smoothing)
        if w_box:
            ar_w = self.pip_wing.viewport_aspect_ratio()
            raw_crop_w = self._compute_wide_crop_rect(w_box, img_w, img_h, target_ar=ar_w, pad_factor=1.45)
            crop_rect_w = self._apply_pip_smoothing(raw_crop_w, "wing", img_w, img_h, force=force)
            if not crop_rect_w.isEmpty():
                crop_img = qimg.copy(crop_rect_w)
                self.pip_wing.update_crop(crop_img)
            else:
                self.pip_wing.update_crop(None)
        else:
            self._smooth_crop_w = None
            self.pip_wing.update_crop(None)

        # Ritaglio Corpo Pilota (Vista Larga Panoramica con camera smoothing)
        if p_box:
            ar_p = self.pip_pilot.viewport_aspect_ratio()
            raw_crop_p = self._compute_wide_crop_rect(p_box, img_w, img_h, target_ar=ar_p, pad_factor=1.50)
            crop_rect_p = self._apply_pip_smoothing(raw_crop_p, "pilot", img_w, img_h, force=force)
            if not crop_rect_p.isEmpty():
                crop_img = qimg.copy(crop_rect_p)
                self.pip_pilot.update_crop(crop_img)
            else:
                self.pip_pilot.update_crop(None)
        else:
            self._smooth_crop_p = None
            self.pip_pilot.update_crop(None)

    @staticmethod
    def _compute_wide_crop_rect(
        box: Tuple[int, int, int, int],
        img_w: int,
        img_h: int,
        target_ar: float = 16.0 / 9.0,
        pad_factor: float = 1.45
    ) -> QRect:
        """
        Calcola un rettangolo di ritaglio ad ampio respiro panoramico ('vista larga')
        centrato sul soggetto. Non stringe mai la visuale in strisce verticali strette
        e riempie l'intera larghezza del viewport PiP senza bande nere laterali.
        """
        bx, by, bw, bh = box
        if bw <= 0 or bh <= 0 or img_w <= 0 or img_h <= 0:
            return QRect()

        cx = bx + bw / 2.0
        cy = by + bh / 2.0

        # Dimensioni minime con margini confortevoli
        min_h = max(int(bh * pad_factor), int(img_h * 0.18))
        min_w = max(int(bw * pad_factor), int(min_h * target_ar), int(img_w * 0.18))

        # Garantisce l'aspect ratio panoramico largo
        if min_w / min_h < target_ar:
            crop_w = int(min_h * target_ar)
            crop_h = min_h
        else:
            crop_w = min_w
            crop_h = int(min_w / target_ar)

        # Limita alle dimensioni massime del fotogramma nativo
        crop_w = min(img_w, crop_w)
        crop_h = min(img_h, max(10, int(crop_w / target_ar)))

        # Coordinate centrate
        x1 = int(cx - crop_w / 2.0)
        y1 = int(cy - crop_h / 2.0)

        # Trattieni la larghezza/altezza piena anche vicino ai bordi del video
        if x1 < 0:
            x1 = 0
        elif x1 + crop_w > img_w:
            x1 = max(0, img_w - crop_w)

        if y1 < 0:
            y1 = 0
        elif y1 + crop_h > img_h:
            y1 = max(0, img_h - crop_h)

        return QRect(x1, y1, crop_w, crop_h)

    @staticmethod
    def _deinterlace_crop(img: QImage) -> QImage:
        """
        Filtro di deinterlacciamento ultra-rapido (<0.1 ms) per eliminare l'effetto pettine
        (scanline combing) dai crop ingranditi dei filmati SIV 1080i.
        """
        w, h = img.width(), img.height()
        if h <= 2 or w <= 0:
            return img

        formatted = img.convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = formatted.bits()
        ptr.setsize(formatted.sizeInBytes())
        arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4))
        # Interpolazione vettoriale veloce con cv2.addWeighted
        cv2.addWeighted(arr[0:-2:2], 0.5, arr[2::2], 0.5, 0, dst=arr[1:-1:2])
        return formatted
