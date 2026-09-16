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
        Localizza il pilota all'interno del cono pendolare alare.
        """
        img_h, img_w, _ = img_rgb.shape

        # Dimensioni base attese in proporzione alla calotta
        base_w = max(60, int(wing_box.w * 0.35))
        base_h = max(75, int(wing_box.h * 0.50))

        # Finestra di ricerca rigorosamente nel cono pendolare sottostante
        roi_y1 = max(0, wing_box.y + int(wing_box.h * 0.85))
        roi_y2 = min(img_h, wing_box.bottom_y + int(wing_box.h * 2.0))
        roi_x1 = max(0, wing_box.center_x - int(wing_box.w * 0.45))
        roi_x2 = min(img_w, wing_box.center_x + int(wing_box.w * 0.45))

        roi_h = roi_y2 - roi_y1
        roi_w = roi_x2 - roi_x1

        if roi_h < 15 or roi_w < 15:
            cx = wing_box.center_x
            cy = min(img_h - base_h // 2, wing_box.bottom_y + int(base_h * 0.75))
            return self._create_clamped_box(cx, cy, base_w, base_h, img_w, img_h, 0.45)

        roi = img_rgb[roi_y1:roi_y2, roi_x1:roi_x2]

        # Contrasto locale del pilota (imbrago/salvagente/casco) rispetto allo sfondo uniforme
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        bg_median = float(np.median(gray_roi))
        diff = cv2.absdiff(gray_roi, int(bg_median))

        std_val = float(np.std(gray_roi))
        thresh_val = max(12, min(35, int(std_val * 1.30)))
        _, p_mask = cv2.threshold(diff, thresh_val, 255, cv2.THRESH_BINARY)

        p_mask = cv2.morphologyEx(p_mask, cv2.MORPH_OPEN, self._k_open)
        p_mask = cv2.morphologyEx(p_mask, cv2.MORPH_CLOSE, self._k_close)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(p_mask, connectivity=8)

        candidates = []
        roi_cx = roi_w / 2.0

        for idx in range(1, num_labels):
            area = stats[idx, cv2.CC_STAT_AREA]
            bcx, bcy = centroids[idx]

            if area < 5 or area > (roi_w * roi_h * 0.50):
                continue

            # Distanza dall'asse pendolare centrale
            dist_to_axis = abs(bcx - roi_cx)
            axis_score = max(0.15, 1.0 - (dist_to_axis / max(1.0, roi_w * 0.5)))

            # Posizione lungo le funi
            y_ratio = bcy / max(1.0, roi_h)
            depth_score = 1.3 if 0.20 <= y_ratio <= 0.85 else 0.7

            # Continuità temporale
            temporal_score = 1.0
            if last_pilot_box is not None:
                last_roi_cx = (last_pilot_box.center_x) - roi_x1
                last_roi_cy = (last_pilot_box.center_y) - roi_y1
                p_dist = np.hypot(bcx - last_roi_cx, bcy - last_roi_cy)
                temporal_score = max(0.2, 1.0 - (p_dist / max(1.0, roi_h * 0.6)))

            score = float(area) * axis_score * depth_score * (temporal_score ** 1.5)
            candidates.append((score, idx))

        if candidates:
            candidates.sort(key=lambda c: c[0], reverse=True)
            best_idx = candidates[0][1]

            blob_cx = int(centroids[best_idx][0]) + roi_x1
            blob_cy = int(centroids[best_idx][1]) + roi_y1
            blob_w = stats[best_idx, cv2.CC_STAT_WIDTH]
            blob_h = stats[best_idx, cv2.CC_STAT_HEIGHT]

            # Inquadratura ergonomica centrata sul baricentro del pilota
            target_w = max(55, int(blob_w * 1.85))
            target_h = max(70, int(blob_h * 1.85))

            # Mantieni proporzioni ergonomiche per il corpo del pilota
            if target_w > target_h * 1.15:
                target_h = int(target_w * 1.1)
            elif target_h > target_w * 1.5:
                target_w = int(target_h * 0.75)

            conf = min(0.95, round(wing_box.confidence * 0.9 + 0.05, 2))
            return self._create_clamped_box(blob_cx, blob_cy, target_w, target_h, img_w, img_h, conf)

        # Fallback pendolare geometrico
        default_cx = wing_box.center_x
        default_cy = min(img_h - base_h // 2, wing_box.bottom_y + int(base_h * 0.75))
        return self._create_clamped_box(default_cx, default_cy, base_w, base_h, img_w, img_h, 0.45)

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
