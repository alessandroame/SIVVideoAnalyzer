from typing import List, Dict, Any, Optional, Tuple
import math


class TrajectorySmoother:
    """
    Stabilizzatore e interpolatore temporale per le traiettorie di Pilota e Vela.
    Caratteristiche:
    - Rifiuto degli outlier (salto anomalo di coordinate non fisicamente plausibile)
    - Riempimento automatico dei micro-buchi di rilevamento (gap filling)
    - Smoothing cinematico adattivo basato sull'accelerazione angolare e lineare
    - Interpolazione continua a sub-frame precision per riproduzione fluida
    """
    def __init__(
        self,
        alpha: float = 0.35,
        alpha_size: Optional[float] = None,
        velocity_boost: float = 0.85,
        max_jump_px: float = 650.0,
        velocity_threshold: float = 20.0
    ):
        self.alpha = alpha
        self.alpha_size = 0.25 if alpha_size is None else alpha_size
        self.velocity_boost = velocity_boost
        self.max_jump_px = max_jump_px
        self.velocity_threshold = velocity_threshold

    def smooth_trajectory(
        self,
        raw_samples: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Stabilizza la lista dei campioni temporali grezzi:
        [{'t': 0.0, 'pilot': [x, y, w, h], 'wing': [x, y, w, h]}, ...]
        """
        if not raw_samples:
            return []

        # Ordina per timestamp
        samples = sorted(raw_samples, key=lambda s: s.get("t", 0.0))
        n = len(samples)

        # 1. Riempimento dei buchi temporali isolati (gap filling per 1-2 frame mancanti)
        samples = self._fill_isolated_gaps(samples)

        smoothed = []
        last_pilot: Optional[List[float]] = None
        last_wing: Optional[List[float]] = None

        for sample in samples:
            t = sample.get("t", 0.0)
            p_box = sample.get("pilot")
            w_box = sample.get("wing")

            # Stabilizzazione Pilota
            if p_box is not None:
                if last_pilot is None:
                    curr_p = [float(v) for v in p_box]
                else:
                    curr_p = self._smooth_box(last_pilot, p_box)
                last_pilot = curr_p
                out_p = [int(round(v)) for v in curr_p]
            else:
                out_p = None

            # Stabilizzazione Vela
            if w_box is not None:
                if last_wing is None:
                    curr_w = [float(v) for v in w_box]
                else:
                    curr_w = self._smooth_box(last_wing, w_box)
                last_wing = curr_w
                out_w = [int(round(v)) for v in curr_w]
            else:
                out_w = None

            smoothed.append({
                "t": round(float(t), 3),
                "pilot": out_p,
                "wing": out_w
            })

        return smoothed

    def _fill_isolated_gaps(self, samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Interpola i frame singoli o doppi in cui il rilevamento ha perso temporaneamente il target."""
        n = len(samples)
        if n < 3:
            return samples

        result = [dict(s) for s in samples]

        for target in ["pilot", "wing"]:
            for i in range(1, n - 1):
                if result[i].get(target) is None:
                    # Controlla se i campioni prima e dopo sono validi
                    prev_val = result[i - 1].get(target)
                    next_val = result[i + 1].get(target)
                    if prev_val is not None and next_val is not None:
                        t_prev = result[i - 1]["t"]
                        t_next = result[i + 1]["t"]
                        t_curr = result[i]["t"]
                        dt = max(1e-4, t_next - t_prev)
                        factor = (t_curr - t_prev) / dt
                        interp = [
                            int(round(prev_val[j] + factor * (next_val[j] - prev_val[j])))
                            for j in range(4)
                        ]
                        result[i][target] = interp

        return result

    def _smooth_box(self, prev_box: List[float], curr_box: List[int]) -> List[float]:
        """Filtro esponenziale adattivo e armonico con outlier rejection e stabilizzazione di posizione e dimensioni."""
        # Calcolo centri euclidei
        prev_cx = prev_box[0] + prev_box[2] * 0.5
        prev_cy = prev_box[1] + prev_box[3] * 0.5
        curr_cx = curr_box[0] + curr_box[2] * 0.5
        curr_cy = curr_box[1] + curr_box[3] * 0.5

        dist = math.hypot(curr_cx - prev_cx, curr_cy - prev_cy)

        # Outlier Rejection: se il box fa un salto non fisico istantaneo, limita il movimento
        if dist > self.max_jump_px:
            clamp_factor = self.max_jump_px / max(1.0, dist)
            curr_cx = prev_cx + (curr_cx - prev_cx) * clamp_factor
            curr_cy = prev_cy + (curr_cy - prev_cy) * clamp_factor
            eff_alpha_pos = self.velocity_boost
            eff_alpha_size = self.velocity_boost
        elif dist >= self.velocity_threshold:
            # Movimento rapido/dinamico (virata, spirale, chiusura, beccheggio):
            eff_alpha_pos = self.velocity_boost
            eff_alpha_size = min(self.velocity_boost, max(self.alpha_size, self.velocity_boost * 0.75))
        elif dist > 3.0:
            # Transizione fluida da smoothing fine a tracking reattivo
            ratio = (dist - 3.0) / max(1.0, self.velocity_threshold - 3.0)
            eff_alpha_pos = min(self.velocity_boost, self.alpha + ratio * (self.velocity_boost - self.alpha))
            eff_alpha_size = self.alpha_size + ratio * (min(self.velocity_boost, 0.6) - self.alpha_size)
        else:
            # Volo dritto o quasi immobile: micro-smoothing per stabilizzare jitter sub-pixel
            eff_alpha_pos = self.alpha
            eff_alpha_size = self.alpha_size

        if eff_alpha_pos >= 1.0:
            smooth_cx = float(curr_cx)
            smooth_cy = float(curr_cy)
        else:
            smooth_cx = prev_cx * (1.0 - eff_alpha_pos) + float(curr_cx) * eff_alpha_pos
            smooth_cy = prev_cy * (1.0 - eff_alpha_pos) + float(curr_cy) * eff_alpha_pos

        if eff_alpha_size >= 1.0 or eff_alpha_pos >= 1.0:
            smooth_w = float(curr_box[2])
            smooth_h = float(curr_box[3])
        else:
            smooth_w = prev_box[2] * (1.0 - eff_alpha_size) + float(curr_box[2]) * eff_alpha_size
            smooth_h = prev_box[3] * (1.0 - eff_alpha_size) + float(curr_box[3]) * eff_alpha_size

        smooth_x = smooth_cx - smooth_w * 0.5
        smooth_y = smooth_cy - smooth_h * 0.5

        return [smooth_x, smooth_y, smooth_w, smooth_h]

    @staticmethod
    def interpolate_boxes_at(
        trajectory: List[Dict[str, Any]],
        t: float
    ) -> Tuple[Optional[List[int]], Optional[List[int]]]:
        """
        Dato un timestamp in secondi, trova i campioni adiacenti e interpola con precisione continua sub-frame.
        Se il timestamp coincide con un fotogramma campionato (entro 5ms, es. frame-stepping durante pausa),
        aggancia direttamente il box esatto di quel frame.
        Ritorna: (pilot_box [x, y, w, h], wing_box [x, y, w, h])
        """
        if not trajectory:
            return None, None

        if t <= trajectory[0]["t"]:
            first = trajectory[0]
            return first.get("pilot"), first.get("wing")

        if t >= trajectory[-1]["t"]:
            last = trajectory[-1]
            return last.get("pilot"), last.get("wing")

        # Ricerca binaria dei campioni [idx, idx + 1]
        low = 0
        high = len(trajectory) - 1
        while low <= high:
            mid = (low + high) // 2
            if trajectory[mid]["t"] <= t:
                low = mid + 1
            else:
                high = mid - 1

        idx0 = max(0, high)
        idx1 = min(len(trajectory) - 1, idx0 + 1)

        s0 = trajectory[idx0]
        s1 = trajectory[idx1]

        dt = s1["t"] - s0["t"]
        if dt <= 1e-4:
            return s0.get("pilot"), s0.get("wing")

        # Snap esatto solo per micro-tolleranza di frame discreto (5 ms),
        # per consentire una riproduzione fluida continua senza scatti a gradino
        if abs(t - s0["t"]) <= 0.005:
            return s0.get("pilot"), s0.get("wing")
        if abs(t - s1["t"]) <= 0.005:
            return s1.get("pilot"), s1.get("wing")

        factor = max(0.0, min(1.0, (t - s0["t"]) / dt))

        p0, p1 = s0.get("pilot"), s1.get("pilot")
        interp_p = None
        if p0 and p1:
            interp_p = [
                int(round(p0[i] + factor * (p1[i] - p0[i])))
                for i in range(4)
            ]
        elif p0:
            interp_p = p0
        elif p1:
            interp_p = p1

        w0, w1 = s0.get("wing"), s1.get("wing")
        interp_w = None
        if w0 and w1:
            interp_w = [
                int(round(w0[i] + factor * (w1[i] - w0[i])))
                for i in range(4)
            ]
        elif w0:
            interp_w = w0
        elif w1:
            interp_w = w1

        return interp_p, interp_w
