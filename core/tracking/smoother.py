from typing import List, Dict, Any, Optional, Tuple


class TrajectorySmoother:
    """
    Stabilizzatore e interpolatore temporale per le traiettorie di Pilota e Vela.
    Applica un filtro di smoothing esponenziale (EMA dinamico) per prevenire
    il jitter dovuto alla telecamera a mano, e fornisce interpolazione lineare
    continua a qualsiasi framerate (sub-frame precision).
    """
    def __init__(self, alpha: float = 0.35, velocity_boost: float = 0.65):
        self.alpha = alpha
        self.velocity_boost = velocity_boost

    def smooth_trajectory(
        self,
        raw_samples: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Filtra la lista dei campioni temporali grezzi:
        [{'t': 0.0, 'pilot': [x, y, w, h], 'wing': [x, y, w, h]}, ...]
        Restituisce la lista con le coordinate stabilizzate.
        """
        if not raw_samples:
            return []

        # Ordina per timestamp
        sorted_samples = sorted(raw_samples, key=lambda s: s.get("t", 0.0))
        smoothed = []

        last_pilot = None
        last_wing = None

        for sample in sorted_samples:
            t = sample.get("t", 0.0)
            p_box = sample.get("pilot")
            w_box = sample.get("wing")

            # Filtro Pilota
            if p_box is not None:
                if last_pilot is None:
                    curr_p = [float(v) for v in p_box]
                else:
                    curr_p = self._smooth_box(last_pilot, p_box)
                last_pilot = curr_p
                out_p = [int(round(v)) for v in curr_p]
            else:
                out_p = None

            # Filtro Vela
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

    def _smooth_box(self, prev_box: List[float], curr_box: List[int]) -> List[float]:
        """EMA con adattamento di velocità dinamica."""
        # Se c'è un movimento rapido (manovra violenta, stallo, spirale), aumenta alpha
        dist = abs(curr_box[0] - prev_box[0]) + abs(curr_box[1] - prev_box[1])
        eff_alpha = self.velocity_boost if dist > 60 else self.alpha

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
        ed esegue un'interpolazione lineare (lerp) continua.
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
