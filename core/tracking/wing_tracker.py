from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np


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
    Rilevatore e tracciatore della vela del parapendio.
    Esegue segmentazione cromatica HSV vettoriale per isolare la vela
    da cielo e specchio d'acqua, calcolando il bounding box ottimale con padding.
    """
    def __init__(self, padding_ratio: float = 0.15, min_pixel_threshold: int = 50):
        self.padding_ratio = padding_ratio
        self.min_pixel_threshold = min_pixel_threshold

    def segment_mask(self, img_rgb: np.ndarray) -> Tuple[np.ndarray, int]:
        """
        Segmenta i pixel della vela dall'immagine RGB (H, W, 3).
        Ritorna la maschera booleana (H, W) e il conteggio dei pixel.
        """
        h, w, _ = img_rgb.shape
        rgb_f = img_rgb.astype(np.float32) / 255.0
        r, g, b = rgb_f[:, :, 0], rgb_f[:, :, 1], rgb_f[:, :, 2]

        cmax = np.maximum(np.maximum(r, g), b)
        cmin = np.minimum(np.minimum(r, g), b)
        delta = cmax - cmin

        h_deg = np.zeros_like(r)
        nonzero = delta > 1e-5
        idx_r = nonzero & (cmax == r)
        idx_g = nonzero & (cmax == g)
        idx_b = nonzero & (cmax == b)

        h_deg[idx_r] = (60.0 * ((g[idx_r] - b[idx_r]) / delta[idx_r])) % 360.0
        h_deg[idx_g] = (60.0 * ((b[idx_g] - r[idx_g]) / delta[idx_g])) + 120.0
        h_deg[idx_b] = (60.0 * ((r[idx_b] - g[idx_b]) / delta[idx_b])) + 240.0

        s = np.zeros_like(r)
        s[cmax > 1e-5] = delta[cmax > 1e-5] / cmax[cmax > 1e-5]
        v = cmax

        # 1. Filtra cielo standard (azzurro / celeste desaturo)
        sky_mask = (h_deg >= 195) & (h_deg <= 240) & (s < 0.50) & (v > 0.45)

        # 2. Filtra lago e foschia neutra
        water_haze_mask = (s < 0.22) & (v < 0.85) & (v > 0.25)

        # 3. Colori saturi e vivaci tipici dei tessuti da parapendio
        vibrant_colors = (s >= 0.25) & (v >= 0.18) & (~sky_mask)
        wing_white = (s < 0.20) & (v >= 0.85)
        wing_black = (s < 0.30) & (v >= 0.05) & (v < 0.25)

        mask = (vibrant_colors | wing_white | wing_black) & (~water_haze_mask) & (v >= 0.05)

        # Rileva e rimuove eventuale specchio d'acqua massivo se penetrato
        blue_lake = (h_deg >= 180) & (h_deg <= 245) & (s < 0.65)
        if np.sum(blue_lake) > (w * h * 0.30):
            mask = mask & (~blue_lake)

        pixel_count = int(np.sum(mask))
        return mask, pixel_count

    def detect(self, img_rgb: np.ndarray) -> Optional[WingBox]:
        """
        Rileva la bounding box della vela all'interno del frame RGB.
        Aggiunge padding proporzionale per consentire la visualizzazione
        completa del profilo alare durante beccheggio e rollio.
        """
        h, w, _ = img_rgb.shape
        mask, pixel_count = self.segment_mask(img_rgb)

        if pixel_count < self.min_pixel_threshold:
            return None

        ys, xs = np.where(mask)
        if len(xs) == 0:
            return None

        # Usa i percentili 1% e 99% per eliminare singoli pixel spuri di riflesso
        if len(xs) > 200:
            x_min = int(np.percentile(xs, 1))
            x_max = int(np.percentile(xs, 99))
            y_min = int(np.percentile(ys, 1))
            y_max = int(np.percentile(ys, 99))
        else:
            x_min = int(np.min(xs))
            x_max = int(np.max(xs))
            y_min = int(np.min(ys))
            y_max = int(np.max(ys))

        bw = max(10, x_max - x_min)
        bh = max(10, y_max - y_min)

        # Aggiungi padding dinamico
        pad_x = int(bw * self.padding_ratio)
        pad_y = int(bh * self.padding_ratio)

        final_x = max(0, x_min - pad_x)
        final_y = max(0, y_min - pad_y)
        final_w = min(w - final_x, bw + 2 * pad_x)
        final_h = min(h - final_y, bh + 2 * pad_y)

        # Calcola confidenza basata sul numero di pixel e regolarità geometrica
        aspect_ratio = final_w / max(1, final_h)
        # Una vela in volo ha solitamente un'apertura alare maggiore dell'altezza
        conf = min(1.0, pixel_count / 10000.0)
        if 0.5 <= aspect_ratio <= 4.5:
            conf = min(1.0, conf + 0.3)

        return WingBox(
            x=final_x,
            y=final_y,
            w=final_w,
            h=final_h,
            confidence=round(conf, 2),
            pixel_count=pixel_count
        )
