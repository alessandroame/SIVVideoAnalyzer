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
        alpha: float = 0.45,
        velocity_boost: float = 0.85,
        max_jump_px: float = 380.0
    ):
        self.alpha = alpha
        self.velocity_boost = velocity_boost
        self.max_jump_px = max_jump_px

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
        """Filtro esponenziale adattivo con outlier rejection."""
        # Distanza euclidea tra i centri
        prev_cx = prev_box[0] + prev_box[2] * 0.5
        prev_cy = prev_box[1] + prev_box[3] * 0.5
        curr_cx = curr_box[0] + curr_box[2] * 0.5
        curr_cy = curr_box[1] + curr_box[3] * 0.5

        dist = math.hypot(curr_cx - prev_cx, curr_cy - prev_cy)

        # Outlier Rejection: se il box fa un salto non fisico istantaneo, limita il movimento
        if dist > self.max_jump_px:
            clamp_factor = self.max_jump_px / max(1.0, dist)
            curr_box = [
                int(round(prev_box[0] + (curr_box[0] - prev_box[0]) * clamp_factor)),
                int(round(prev_box[1] + (curr_box[1] - prev_box[1]) * clamp_factor)),
                curr_box[2],
                curr_box[3]
            ]
            eff_alpha = self.alpha
        elif dist > 40:
            # Movimento rapido (virata/spirale): aumenta reattività
            eff_alpha = min(self.velocity_boost, self.alpha + (dist / 200.0) * (self.velocity_boost - self.alpha))
        else:
            # Volo dritto o scorrimento lento: smoothing massimo per stabilizzare camera shake
            eff_alpha = self.alpha

        smoothed = []
        for p, c in zip(prev_box, curr_box):
            val = p * (1.0 - eff_alpha) + float(c) * eff_alpha
            smoothed.append(val)
        return smoothed

    @staticmethod
    def interpolate_boxes_at(
        trajectory: List[Dict[str, Any]],
        t: float
    ) -> Tuple[Optional[List[int]], Optional[List[int]]]:
        """
        Dato un timestamp in secondi, trova i due campioni adiacenti
        ed esegue un'interpolazione lineare continua.
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
