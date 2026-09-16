from dataclasses import dataclass
from typing import Optional, Tuple, List
import numpy as np
import cv2


@dataclass
class WingBox:
    """Bounding box della vela in coordinate pixel assolute [x, y, w, h]."""
    x: int
    y: int
    w: int
    h: int
    confidence: float
    pixel_count: int

    @property
    def center_x(self) -> int:
        return self.x + self.w // 2

    @property
    def center_y(self) -> int:
        return self.y + self.h // 2

    @property
    def bottom_y(self) -> int:
        return self.y + self.h

    def to_list(self) -> list:
        return [int(self.x), int(self.y), int(self.w), int(self.h)]


class WingTracker:
    """
    Rilevatore e tracciatore avanzato della vela del parapendio con OpenCV.
    Isola specificamente la calotta alare senza inglobare il pilota o i riflessi
    di cielo e lago.
    """
    def __init__(
        self,
        padding_ratio: float = 0.10,
        min_pixel_threshold: int = 40,
        target_colors: Optional[List[str]] = None
    ):
        self.padding_ratio = padding_ratio
        self.min_pixel_threshold = min_pixel_threshold
        self.target_colors = [c.lower().strip() for c in target_colors] if target_colors else []

        self._kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self._kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))

    def set_target_colors(self, colors: Optional[List[str]]):
        """Imposta i colori noti della vela per guidare l'estrazione."""
        self.target_colors = [c.lower().strip() for c in colors] if colors else []

    def _build_canopy_mask(self, hsv: np.ndarray) -> np.ndarray:
        """
        Costruisce la maschera della sola calotta (tessuto ripstop),
        escludendo completamente cielo, lago e pilot harness scuro.
        """
        H = hsv[:, :, 0]
        S = hsv[:, :, 1]
        V = hsv[:, :, 2]

        # 1. Cielo azzurro/blu/celeste (OpenCV H: 0..180 -> blu è ~90..135)
        # Il cielo sereno in quota presenta spesso saturazione elevata (fino a 180+)
        blue_sky = (H >= 88) & (H <= 135) & (S >= 35) & (V >= 65)

        # 2. Lago / acqua / foschia neutra
        water_haze = (S < 35) & (V >= 55) & (V <= 200)

        # 3. Calotta: fuori dal cielo blu e dal lago neutro, con luminosità sufficiente
        # NB: Non includiamo tonalità scure (V < 50) per evitare di fondere il corpo del pilota
        canopy = (~blue_sky) & (~water_haze) & (V >= 50)

        # Se sono indicati colori bersaglio dal pilota/sidecar, privilegia quelle bande
        if self.target_colors:
            boost = np.zeros_like(H, dtype=bool)
            for c in self.target_colors:
                if "ross" in c:
                    boost |= ((H < 12) | (H >= 165)) & (S >= 45) & (V >= 40)
                elif "aranc" in c:
                    boost |= (H >= 10) & (H < 25) & (S >= 50) & (V >= 40)
                elif "giall" in c:
                    boost |= (H >= 22) & (H < 38) & (S >= 50) & (V >= 40)
                elif "lime" in c:
                    boost |= (H >= 35) & (H < 50) & (S >= 50) & (V >= 40)
                elif "verd" in c:
                    boost |= (H >= 45) & (H < 85) & (S >= 45) & (V >= 35)
                elif "cian" in c or "azzurr" in c:
                    boost |= (H >= 82) & (H < 100) & (S >= 60) & (V >= 60)
                elif "blu" in c:
                    boost |= (H >= 100) & (H < 135) & (S >= 160) & (V >= 40)
                elif "viol" in c:
                    boost |= (H >= 130) & (H < 155) & (S >= 45) & (V >= 35)
                elif "ros" in c or "pink" in c:
                    boost |= (H >= 150) & (H < 170) & (S >= 45) & (V >= 40)
                elif "bianc" in c:
                    boost |= (S < 35) & (V >= 215) & (~blue_sky)
            if np.any(boost) and np.sum(boost) > self.min_pixel_threshold:
                canopy = canopy | boost

        return (canopy.astype(np.uint8)) * 255

    def detect(
        self,
        img_rgb: np.ndarray,
        last_wing_box: Optional[WingBox] = None
    ) -> Optional[WingBox]:
        """
        Rileva e isola la calotta della vela nell'immagine RGB.
        Esegue blob detection, filtraggio geometrico e aggancio temporale.
        """
        orig_h, orig_w, _ = img_rgb.shape
        if orig_h < 20 or orig_w < 20:
            return None

        # Scala per elaborazione ultra-rapida (>100 fps)
        scale = 1.0
        if orig_w > 960:
            scale = 0.5
            proc_img = cv2.resize(img_rgb, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        else:
            proc_img = img_rgb

        h, w, _ = proc_img.shape

        # Conversione HSV
        hsv = cv2.cvtColor(proc_img, cv2.COLOR_RGB2HSV)
        bin_mask = self._build_canopy_mask(hsv)

        # Pulizia morfologica (rimuove rumore puntiforme e unisce le celle alari)
        bin_mask = cv2.morphologyEx(bin_mask, cv2.MORPH_OPEN, self._kernel_open)
        bin_mask = cv2.morphologyEx(bin_mask, cv2.MORPH_CLOSE, self._kernel_close)

        # Connected Components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bin_mask, connectivity=8)
        if num_labels <= 1:
            return self._temporal_fallback(last_wing_box)

        best_idx = -1
        best_score = -1.0
        scaled_min_pixels = int(self.min_pixel_threshold * (scale ** 2))
        max_allowed_area = int(w * h * 0.40)

        for idx in range(1, num_labels):
            area = stats[idx, cv2.CC_STAT_AREA]
            if area < scaled_min_pixels or area > max_allowed_area:
                continue

            bw = stats[idx, cv2.CC_STAT_WIDTH]
            bh = stats[idx, cv2.CC_STAT_HEIGHT]
            aspect = bw / max(1, bh)

            # Il profilo di una calotta in volo ha aspect ratio tra 0.4 e 4.8
            if aspect < 0.35 or aspect > 5.0:
                continue

            # Punteggio base: area e proporzione geometrica
            score = float(area)
            if 1.1 <= aspect <= 3.8:
                score *= 1.35
            elif 0.8 <= aspect <= 4.5:
                score *= 1.10

            # Continuità spaziale con il frame precedente
            if last_wing_box is not None:
                last_cx = (last_wing_box.center_x) * scale
                last_cy = (last_wing_box.center_y) * scale
                dist = np.hypot(centroids[idx][0] - last_cx, centroids[idx][1] - last_cy)
                proximity_factor = max(0.2, 1.0 - (dist / (w * 0.6)))
                score *= (proximity_factor ** 1.5)

            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx <= 0:
            return self._temporal_fallback(last_wing_box)

        # Riconversione a coordinate native
        inv_scale = 1.0 / scale
        raw_x = int(stats[best_idx, cv2.CC_STAT_LEFT] * inv_scale)
        raw_y = int(stats[best_idx, cv2.CC_STAT_TOP] * inv_scale)
        raw_w = int(stats[best_idx, cv2.CC_STAT_WIDTH] * inv_scale)
        raw_h = int(stats[best_idx, cv2.CC_STAT_HEIGHT] * inv_scale)
        pixel_count = int(stats[best_idx, cv2.CC_STAT_AREA] * (inv_scale ** 2))

        # Padding proporzionale calibrato
        pad_x = int(raw_w * self.padding_ratio)
        pad_y = int(raw_h * self.padding_ratio)

        final_x = max(0, raw_x - pad_x)
        final_y = max(0, raw_y - pad_y)
        final_w = min(orig_w - final_x, raw_w + 2 * pad_x)
        final_h = min(orig_h - final_y, raw_h + 2 * pad_y)

        conf = min(1.0, 0.5 + (pixel_count / 15000.0) * 0.5)

        return WingBox(
            x=final_x,
            y=final_y,
            w=final_w,
            h=final_h,
            confidence=round(conf, 2),
            pixel_count=pixel_count
        )

    def _temporal_fallback(self, last_wing_box: Optional[WingBox]) -> Optional[WingBox]:
        """In caso di perdita momentanea del target, preserva l'ultima posizione valida."""
        if last_wing_box is not None:
            return WingBox(
                x=last_wing_box.x,
                y=last_wing_box.y,
                w=last_wing_box.w,
                h=last_wing_box.h,
                confidence=max(0.2, round(last_wing_box.confidence * 0.85, 2)),
                pixel_count=last_wing_box.pixel_count
            )
        return None
