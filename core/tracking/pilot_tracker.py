import os
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
from core.tracking.wing_tracker import WingBox


@dataclass
class PilotBox:
    """Bounding box del corpo del pilota in coordinate pixel [x, y, w, h]."""
    x: int
    y: int
    w: int
    h: int
    confidence: float

    @property
    def center_x(self) -> int:
        return self.x + self.w // 2

    @property
    def center_y(self) -> int:
        return self.y + self.h // 2

    def to_list(self) -> list:
        return [int(self.x), int(self.y), int(self.w), int(self.h)]


class PilotTracker:
    """
    Rilevatore e tracciatore del corpo del pilota (imbrago, busto, comandi).
    Sfrutta la dinamica fisica del pendolo vincolato alla vela (geometria funi)
    e l'analisi del gradiente ad alto contrasto per agganciare con precisione
    il pilota sospeso sotto la calotta.
    """
    def __init__(self, onnx_model_path: Optional[str] = None):
        self.onnx_model_path = onnx_model_path
        self._onnx_session = None
        self._init_onnx_if_available()

    def _init_onnx_if_available(self):
        """Inizializza onnxruntime se è presente un modello person/pose nella cartella models."""
        if self.onnx_model_path and os.path.exists(self.onnx_model_path):
            try:
                import onnxruntime as ort
                self._onnx_session = ort.InferenceSession(
                    self.onnx_model_path,
                    providers=["CPUExecutionProvider"]
                )
            except Exception:
                self._onnx_session = None

    def detect(
        self,
        img_rgb: np.ndarray,
        wing_box: Optional[WingBox] = None,
        last_pilot_box: Optional[PilotBox] = None
    ) -> Optional[PilotBox]:
        """
        Rileva la bounding box del pilota.
        Se la vela è nota, cerca lungo l'asse pendolare sotto il centro della calotta.
        """
        h, w, _ = img_rgb.shape

        if wing_box is not None:
            return self._detect_under_wing(img_rgb, wing_box)

        if last_pilot_box is not None:
            # Fallback temporale: mantieni l'ultima posizione valida
            return PilotBox(
                x=last_pilot_box.x,
                y=last_pilot_box.y,
                w=last_pilot_box.w,
                h=last_pilot_box.h,
                confidence=max(0.2, last_pilot_box.confidence * 0.9)
            )

        return None

    def _detect_under_wing(self, img_rgb: np.ndarray, wing_box: WingBox) -> Optional[PilotBox]:
        """
        Localizza il pilota nell'area pendolare sottostante la vela.
        Analizza i gradienti e la varianza locale per trovare il baricentro dell'imbrago.
        """
        img_h, img_w, _ = img_rgb.shape

        # Stima dimensioni del riquadro pilota in proporzione alla vela
        # In un parapendio l'altezza totale del sistema pilota+funi è ~0.8-1.4 volte l'apertura alare
        target_w = max(70, int(wing_box.w * 0.42))
        target_h = max(90, int(wing_box.h * 0.65))

        # Finestra di ricerca verticale sotto la vela
        search_y_start = min(img_h - 10, max(0, wing_box.bottom_y - int(wing_box.h * 0.15)))
        search_y_end = min(img_h, wing_box.bottom_y + int(wing_box.h * 1.8))
        search_x_start = max(0, wing_box.center_x - int(wing_box.w * 0.40))
        search_x_end = min(img_w, wing_box.center_x + int(wing_box.w * 0.40))

        if search_y_end - search_y_start < 30 or search_x_end - search_x_start < 30:
            # Fallback geometrico diretto
            cx = wing_box.center_x
            cy = min(img_h - target_h // 2, wing_box.bottom_y + target_h // 2)
            return self._create_clamped_box(cx, cy, target_w, target_h, img_w, img_h, 0.6)

        sub_region = img_rgb[search_y_start:search_y_end, search_x_start:search_x_end]

        # Converti regione in scala di grigi
        gray = (0.299 * sub_region[:, :, 0] + 0.587 * sub_region[:, :, 1] + 0.114 * sub_region[:, :, 2]).astype(np.float32)

        # Calcola gradiente Sobel approssimato (differenze assolute) per rilevare bordi di pilota/imbrago/funi
        grad_y = np.abs(gray[1:, :] - gray[:-1, :])
        grad_x = np.abs(gray[:, 1:] - gray[:, :-1])
        grad_mag = np.zeros_like(gray)
        grad_mag[:-1, :] += grad_y
        grad_mag[:, :-1] += grad_x

        # Filtra gradiente di fondo (rumore leggero dell'acqua o cielo)
        thresh = np.percentile(grad_mag, 85)
        high_grad = grad_mag > max(15.0, thresh)

        ys, xs = np.where(high_grad)
        if len(xs) > 20:
            # Baricentro ponderato
            centroid_x = int(np.median(xs)) + search_x_start
            centroid_y = int(np.median(ys)) + search_y_start
            conf = min(0.95, wing_box.confidence)
        else:
            # Default pendolare standard
            centroid_x = wing_box.center_x
            centroid_y = min(img_h - target_h // 2, wing_box.bottom_y + int(target_h * 0.6))
            conf = 0.5

        return self._create_clamped_box(centroid_x, centroid_y, target_w, target_h, img_w, img_h, conf)

    def _create_clamped_box(
        self,
        cx: int,
        cy: int,
        bw: int,
        bh: int,
        max_w: int,
        max_h: int,
        conf: float
    ) -> PilotBox:
        x = max(0, min(cx - bw // 2, max_w - bw))
        y = max(0, min(cy - bh // 2, max_h - bh))
        return PilotBox(
            x=int(x),
            y=int(y),
            w=int(bw),
            h=int(bh),
            confidence=round(conf, 2)
        )
