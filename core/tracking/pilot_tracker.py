from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import cv2

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
    Rilevatore e tracciatore ad alta precisione del corpo del pilota (imbrago, busto, comandi).
    Sfrutta:
    - Il vincolo geometrico del cono pendolare rigorosamente sotto la calotta
    - Saliency e contrasto adattivo locale contro cielo e acqua
    - Connected Component Analysis per centrare imbrago, casco e azione delle braccia
    - Inerzia fisica e continuità temporale
    """
    def __init__(self, onnx_model_path: Optional[str] = None):
        self.onnx_model_path = onnx_model_path
        self._k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self._k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def detect(
        self,
        img_rgb: np.ndarray,
        wing_box: Optional[WingBox] = None,
        last_pilot_box: Optional[PilotBox] = None
    ) -> Optional[PilotBox]:
        """
        Rileva e inquadra il corpo del pilota.
        Se la vela è nota, analizza il cono pendolare sottostante.
        """
        img_h, img_w, _ = img_rgb.shape
        if img_h < 20 or img_w < 20:
            return None

        if wing_box is not None:
            return self._detect_under_wing(img_rgb, wing_box, last_pilot_box)

        if last_pilot_box is not None:
            return PilotBox(
                x=last_pilot_box.x,
                y=last_pilot_box.y,
                w=last_pilot_box.w,
                h=last_pilot_box.h,
                confidence=max(0.2, round(last_pilot_box.confidence * 0.85, 2))
            )

        return None

    def _detect_under_wing(
        self,
        img_rgb: np.ndarray,
        wing_box: WingBox,
        last_pilot_box: Optional[PilotBox] = None
    ) -> Optional[PilotBox]:
        """
        Localizza il pilota all'interno del cono pendolare alare sfruttando:
        1. Darkness Saliency (Dark-Core): l'imbrago in cordura e il cono d'ombra sotto la vela
           costituiscono la porzione a minima luminanza del settore pendolare.
        2. Inquadratura Anatomica Calibrata (Braccia + Busto + Gambe): l'inquadratura racchiude
           l'intera statura in volo (mani sui comandi/freni in alto e gambe/scarponi in basso per
           il contrasto col peso).
        """
        img_h, img_w, _ = img_rgb.shape

        # Finestra di ricerca estesa per catturare oscillazioni dinamiche (wingover, spirali, chiusure)
        roi_y1 = max(0, wing_box.y + int(wing_box.h * 0.60))
        roi_y2 = min(img_h, wing_box.bottom_y + int(wing_box.h * 3.2))
        roi_x1 = max(0, wing_box.center_x - int(wing_box.w * 0.85))
        roi_x2 = min(img_w, wing_box.center_x + int(wing_box.w * 0.85))

        # Se abbiamo la posizione del fotogramma precedente, includiamo il suo intorno nella ROI
        if last_pilot_box is not None:
            margin_x = int(last_pilot_box.w * 1.5)
            margin_y = int(last_pilot_box.h * 1.5)
            roi_x1 = min(roi_x1, max(0, last_pilot_box.x - margin_x))
            roi_x2 = max(roi_x2, min(img_w, last_pilot_box.x + last_pilot_box.w + margin_x))
            roi_y1 = min(roi_y1, max(0, last_pilot_box.y - margin_y))
            roi_y2 = max(roi_y2, min(img_h, last_pilot_box.y + last_pilot_box.h + margin_y))

        roi_h = roi_y2 - roi_y1
        roi_w = roi_x2 - roi_x1

        if roi_h < 15 or roi_w < 15:
            if last_pilot_box is not None:
                return PilotBox(
                    x=last_pilot_box.x,
                    y=last_pilot_box.y,
                    w=last_pilot_box.w,
                    h=last_pilot_box.h,
                    confidence=max(0.25, round(last_pilot_box.confidence * 0.90, 2))
                )
            base_w = max(45, int(wing_box.w * 0.32))
            base_h = max(60, int(wing_box.h * 0.52))
            cx = wing_box.center_x
            cy = min(img_h - base_h // 2, wing_box.bottom_y + int(base_h * 0.75))
            return self._create_clamped_box(cx, cy, base_w, base_h, img_w, img_h, 0.45)

        roi = img_rgb[roi_y1:roi_y2, roi_x1:roi_x2]
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)

        bg_mode = float(np.median(gray_roi))
        min_val = float(gray_roi.min())
        spread = bg_mode - min_val

        # Darkness Saliency: isola i pixel del nucleo scuro (imbrago) anche in condizioni di foschia
        if spread >= 4.0:
            dark_thresh = bg_mode - max(3.5, spread * 0.35)
            p_mask = (gray_roi <= dark_thresh).astype(np.uint8) * 255
            p_mask = cv2.morphologyEx(p_mask, cv2.MORPH_OPEN, self._k_open)
            p_mask = cv2.morphologyEx(p_mask, cv2.MORPH_CLOSE, self._k_close)
        else:
            p_mask = np.zeros_like(gray_roi, dtype=np.uint8)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(p_mask, connectivity=8)

        candidates = []
        roi_cx = roi_w / 2.0

        for idx in range(1, num_labels):
            area = stats[idx, cv2.CC_STAT_AREA]
            bcx, bcy = centroids[idx]

            # Filtra blob minuscoli (< 4px) o eccessivi (> 40% della ROI)
            if area < 4 or area > (roi_w * roi_h * 0.40):
                continue

            # Densità di oscurità nel blob: più è scuro l'imbrago rispetto allo sfondo, maggiore è il punteggio
            blob_mask = (labels == idx)
            mean_intensity = float(np.mean(gray_roi[blob_mask]))
            darkness_factor = max(0.25, (bg_mode - mean_intensity) / max(1.0, spread))

            # Distanza dall'asse pendolare centrale: tolleranza elevata per manovre SIV disassate
            dist_to_axis = abs(bcx - roi_cx)
            axis_score = max(0.40, 1.0 - (dist_to_axis / max(1.0, roi_w * 0.70)))

            # Posizione lungo le funi (profondità pendolare)
            y_ratio = bcy / max(1.0, roi_h)
            depth_score = 1.3 if 0.15 <= y_ratio <= 0.90 else 0.7

            # Continuità temporale fluida senza penalizzazioni esponenziali
            temporal_score = 1.0
            if last_pilot_box is not None:
                last_roi_cx = (last_pilot_box.center_x) - roi_x1
                last_roi_cy = (last_pilot_box.center_y) - roi_y1
                p_dist = np.hypot(bcx - last_roi_cx, bcy - last_roi_cy)
                temporal_score = max(0.40, 1.0 - (p_dist / max(1.0, roi_h * 1.2)))

            score = float(area) * darkness_factor * axis_score * depth_score * temporal_score
            candidates.append((score, idx))

        if candidates:
            candidates.sort(key=lambda c: c[0], reverse=True)
            best_idx = candidates[0][1]

            blob_cx = int(centroids[best_idx][0]) + roi_x1
            blob_cy = int(centroids[best_idx][1]) + roi_y1
            blob_w = stats[best_idx, cv2.CC_STAT_WIDTH]
            blob_h = stats[best_idx, cv2.CC_STAT_HEIGHT]

            # Inquadratura Anatomica Calibrata (Braccia + Busto + Gambe):
            # 1. Larghezza proporzionata alla calotta e all'apertura braccia sui comandi
            min_w = max(45, int(wing_box.w * 0.32))
            min_h = max(60, int(wing_box.h * 0.52))

            target_w = max(min_w, int(blob_w * 1.75))
            target_h = max(min_h, int(blob_h * 1.85))

            # 2. Rapporto antropometrico pilota in volo (H/W tipico 1.25x - 1.55x)
            if target_h < int(target_w * 1.25):
                target_h = int(target_w * 1.35)
            elif target_h > int(target_w * 1.60):
                target_w = int(target_h / 1.40)

            # 3. Centratura ergonomica: il Dark-Core è l'imbrago/seduta (baricentro).
            # - Verso l'alto: ~42% dell'altezza (testa, bretelle, mani sui comandi libere/alte).
            # - Verso il basso: ~58% dell'altezza (cosciali, gambe, piedi e contrasto di peso).
            pilot_x = blob_cx - target_w // 2
            pilot_y = blob_cy - int(target_h * 0.42)

            conf = min(0.95, round(wing_box.confidence * 0.9 + 0.05, 2))
            return self._create_clamped_box_from_top_left(
                pilot_x, pilot_y, target_w, target_h, img_w, img_h, conf
            )

        # Fallback inerziale: se perduto per 1 frame, mantieni l'ultima posizione reale anziché saltare al centro vela
        if last_pilot_box is not None:
            return PilotBox(
                x=last_pilot_box.x,
                y=last_pilot_box.y,
                w=last_pilot_box.w,
                h=last_pilot_box.h,
                confidence=max(0.25, round(last_pilot_box.confidence * 0.90, 2))
            )

        # Fallback pendolare geometrico iniziale
        base_w = max(45, int(wing_box.w * 0.32))
        base_h = max(60, int(wing_box.h * 0.52))
        default_cx = wing_box.center_x
        default_cy = min(img_h - base_h // 2, wing_box.bottom_y + int(base_h * 0.75))
        return self._create_clamped_box(default_cx, default_cy, base_w, base_h, img_w, img_h, 0.45)

    def _create_clamped_box_from_top_left(
        self,
        x: int,
        y: int,
        bw: int,
        bh: int,
        max_w: int,
        max_h: int,
        conf: float
    ) -> PilotBox:
        clamped_x = max(0, min(x, max_w - bw))
        clamped_y = max(0, min(y, max_h - bh))
        return PilotBox(
            x=int(clamped_x),
            y=int(clamped_y),
            w=int(bw),
            h=int(bh),
            confidence=round(conf, 2)
        )

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
