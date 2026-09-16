from typing import Dict, Any, List, Optional, Tuple
import math


class KeyframeManager:
    """
    Gestore della correzione interattiva delle traiettorie tramite Keyframe.
    Supporta:
    - Architettura non distruttiva (conservazione di 'raw_trajectory')
    - Delta-blending con curva Hermite/Smoothstep (3w^2 - 2w^3) per preservare
      i micro-movimenti e la dinamica naturale registrata dall'AI
    - Decadimento graduale alle estremità temporali (finestra di transizione fluida)
    - Ripristino istantaneo al tracciamento grezzo AI
    """

    DEFAULT_TRANSITION_WINDOW = 2.5  # secondi di transizione fluida per keyframe isolati o estremi

    @staticmethod
    def ensure_raw_trajectory(tracking_dict: Dict[str, Any]) -> None:
        """Assicura che esista una copia immutabile della traiettoria grezza AI."""
        if "raw_trajectory" not in tracking_dict or not tracking_dict["raw_trajectory"]:
            current_traj = tracking_dict.get("trajectory", [])
            # Copia profonda dei campioni
            tracking_dict["raw_trajectory"] = [
                {
                    "t": s.get("t", 0.0),
                    "pilot": list(s["pilot"]) if s.get("pilot") else None,
                    "wing": list(s["wing"]) if s.get("wing") else None
                }
                for s in current_traj
            ]

    @staticmethod
    def get_keyframes(tracking_dict: Dict[str, Any], subject: Optional[str] = None) -> Any:
        """Restituisce la lista di keyframe per il soggetto specificato o l'intero dizionario."""
        kfs = tracking_dict.get("keyframes")
        if not isinstance(kfs, dict):
            kfs = {"pilot": [], "wing": []}
            tracking_dict["keyframes"] = kfs

        if subject:
            return kfs.get(subject, [])
        return kfs

    @classmethod
    def add_keyframe(
        cls,
        tracking_dict: Dict[str, Any],
        subject: str,
        t: float,
        box: List[int],
        transition_window: float = DEFAULT_TRANSITION_WINDOW
    ) -> None:
        """
        Aggiunge o aggiorna un keyframe per il soggetto ('pilot' o 'wing') al tempo t.
        Ricalcola immediatamente la traiettoria 'trajectory'.
        """
        if subject not in ("pilot", "wing"):
            raise ValueError(f"Soggetto non valido: {subject}. Atteso 'pilot' o 'wing'.")

        cls.ensure_raw_trajectory(tracking_dict)
        kfs = cls.get_keyframes(tracking_dict)
        subj_kfs = kfs.setdefault(subject, [])

        t_rounded = round(float(t), 3)
        clean_box = [int(round(v)) for v in box[:4]]

        # Controlla se esiste già un keyframe vicino (entro 0.05s) per aggiornarlo
        updated = False
        for kf in subj_kfs:
            if abs(kf.get("t", 0.0) - t_rounded) <= 0.05:
                kf["t"] = t_rounded
                kf["box"] = clean_box
                updated = True
                break

        if not updated:
            subj_kfs.append({"t": t_rounded, "box": clean_box})

        # Ordina i keyframe temporalmente
        subj_kfs.sort(key=lambda k: k.get("t", 0.0))

        # Ricalcola la traiettoria
        cls.recalculate_trajectory(tracking_dict, transition_window=transition_window)

    @classmethod
    def remove_keyframe(
        cls,
        tracking_dict: Dict[str, Any],
        subject: str,
        t: float,
        tolerance: float = 0.35,
        transition_window: float = DEFAULT_TRANSITION_WINDOW
    ) -> bool:
        """Rimuove il keyframe più vicino a t (entro la tolleranza)."""
        kfs = cls.get_keyframes(tracking_dict)
        subj_kfs = kfs.get(subject, [])
        if not subj_kfs:
            return False

        original_len = len(subj_kfs)
        kfs[subject] = [kf for kf in subj_kfs if abs(kf.get("t", 0.0) - t) > tolerance]

        if len(kfs[subject]) < original_len:
            cls.recalculate_trajectory(tracking_dict, transition_window=transition_window)
            return True
        return False

    @classmethod
    def reset_keyframes(cls, tracking_dict: Dict[str, Any]) -> None:
        """Ripristina la traiettoria originale da raw_trajectory e rimuove tutti i keyframe."""
        if "raw_trajectory" in tracking_dict and tracking_dict["raw_trajectory"]:
            tracking_dict["trajectory"] = [
                {
                    "t": s.get("t", 0.0),
                    "pilot": list(s["pilot"]) if s.get("pilot") else None,
                    "wing": list(s["wing"]) if s.get("wing") else None
                }
                for s in tracking_dict["raw_trajectory"]
            ]
        tracking_dict["keyframes"] = {"pilot": [], "wing": []}

    @classmethod
    def recalculate_trajectory(
        cls,
        tracking_dict: Dict[str, Any],
        transition_window: float = DEFAULT_TRANSITION_WINDOW
    ) -> None:
        """
        Ricalcola la lista 'trajectory' unendo 'raw_trajectory' con i keyframe manuali.
        Utilizza un'interpolazione smoothstep (Hermite cubic) su ciascun asse x, y, w, h.
        """
        cls.ensure_raw_trajectory(tracking_dict)
        raw_samples = tracking_dict.get("raw_trajectory", [])
        if not raw_samples:
            return

        keyframes_all = cls.get_keyframes(tracking_dict)
        pilot_kfs = keyframes_all.get("pilot", [])
        wing_kfs = keyframes_all.get("wing", [])

        # Se non ci sono keyframe in assoluto, la traiettoria coincide con la grezza
        if not pilot_kfs and not wing_kfs:
            tracking_dict["trajectory"] = [
                {
                    "t": s.get("t", 0.0),
                    "pilot": list(s["pilot"]) if s.get("pilot") else None,
                    "wing": list(s["wing"]) if s.get("wing") else None
                }
                for s in raw_samples
            ]
            return

        # Mappa temporale dei campioni raw per rapida ricerca binaria o accesso
        times = [s["t"] for s in raw_samples]
        new_trajectory = []

        for sample in raw_samples:
            t = sample["t"]
            raw_p = sample.get("pilot")
            raw_w = sample.get("wing")

            corr_p = cls._calculate_subject_box_at(
                t=t,
                raw_box=raw_p,
                keyframes=pilot_kfs,
                raw_samples=raw_samples,
                times=times,
                subject="pilot",
                window=transition_window
            )

            corr_w = cls._calculate_subject_box_at(
                t=t,
                raw_box=raw_w,
                keyframes=wing_kfs,
                raw_samples=raw_samples,
                times=times,
                subject="wing",
                window=transition_window
            )

            new_trajectory.append({
                "t": t,
                "pilot": corr_p,
                "wing": corr_w
            })

        tracking_dict["trajectory"] = new_trajectory

    @classmethod
    def _calculate_subject_box_at(
        cls,
        t: float,
        raw_box: Optional[List[int]],
        keyframes: List[Dict[str, Any]],
        raw_samples: List[Dict[str, Any]],
        times: List[float],
        subject: str,
        window: float
    ) -> Optional[List[int]]:
        """Calcola la box corretta per un soggetto a un dato timestamp."""
        if not keyframes:
            return raw_box

        # Caso 1: t è precedente o uguale al primo keyframe
        if t <= keyframes[0]["t"]:
            kf0 = keyframes[0]
            t0 = kf0["t"]
            raw0 = cls._get_raw_at_time(t0, raw_samples, subject)
            delta0 = cls._compute_delta(kf0["box"], raw0)

            if t >= t0 - 1e-4:
                smooth_factor = 1.0
            elif window <= 1e-4:
                return raw_box
            else:
                t_start = t0 - window
                if t < t_start:
                    return raw_box
                ratio = (t - t_start) / max(1e-4, t0 - t_start)
                smooth_factor = cls._smoothstep(ratio)

            return cls._apply_delta_or_interp(
                raw_box=raw_box,
                delta=[smooth_factor * d for d in delta0],
                fallback_target=kf0["box"],
                factor=smooth_factor
            )

        # Caso 2: t è successivo o uguale all'ultimo keyframe
        if t >= keyframes[-1]["t"]:
            kf_last = keyframes[-1]
            t_last = kf_last["t"]
            raw_last = cls._get_raw_at_time(t_last, raw_samples, subject)
            delta_last = cls._compute_delta(kf_last["box"], raw_last)

            if t <= t_last + 1e-4:
                smooth_factor = 1.0
            elif window <= 1e-4:
                return raw_box
            else:
                t_end = t_last + window
                if t > t_end:
                    return raw_box
                ratio = (t_end - t) / max(1e-4, t_end - t_last)
                smooth_factor = cls._smoothstep(ratio)

            return cls._apply_delta_or_interp(
                raw_box=raw_box,
                delta=[smooth_factor * d for d in delta_last],
                fallback_target=kf_last["box"],
                factor=smooth_factor
            )

        # Caso 3: t è compreso tra due keyframe kf_prev e kf_next
        kf_prev = keyframes[0]
        kf_next = keyframes[-1]
        for i in range(len(keyframes) - 1):
            if keyframes[i]["t"] <= t <= keyframes[i + 1]["t"]:
                kf_prev = keyframes[i]
                kf_next = keyframes[i + 1]
                break

        t_prev = kf_prev["t"]
        t_next = kf_next["t"]
        dt = max(1e-4, t_next - t_prev)
        w = max(0.0, min(1.0, (t - t_prev) / dt))
        s = cls._smoothstep(w)

        raw_prev = cls._get_raw_at_time(t_prev, raw_samples, subject)
        raw_next = cls._get_raw_at_time(t_next, raw_samples, subject)

        delta_prev = cls._compute_delta(kf_prev["box"], raw_prev)
        delta_next = cls._compute_delta(kf_next["box"], raw_next)

        if raw_box is not None:
            # Delta blending: (1 - s) * delta_prev + s * delta_next
            interp_delta = [
                (1.0 - s) * delta_prev[j] + s * delta_next[j]
                for j in range(4)
            ]
            return [
                int(round(raw_box[j] + interp_delta[j]))
                for j in range(4)
            ]
        else:
            # Se raw_box è None (soggetto perso), interpola direttamente le box assolute
            b_prev = kf_prev["box"]
            b_next = kf_next["box"]
            return [
                int(round((1.0 - s) * b_prev[j] + s * b_next[j]))
                for j in range(4)
            ]

    @staticmethod
    def _smoothstep(x: float) -> float:
        """Curva cubica Hermite smoothstep 3x^2 - 2x^3 con accelerazione e decelerazione morbida."""
        clamped = max(0.0, min(1.0, x))
        return clamped * clamped * (3.0 - 2.0 * clamped)

    @staticmethod
    def _compute_delta(kf_box: List[int], raw_box: Optional[List[int]]) -> List[float]:
        """Calcola il vettore scostamento [dx, dy, dw, dh] del keyframe rispetto al rilevamento base."""
        if not raw_box:
            return [0.0, 0.0, 0.0, 0.0]
        return [float(kf_box[i] - raw_box[i]) for i in range(4)]

    @staticmethod
    def _apply_delta_or_interp(
        raw_box: Optional[List[int]],
        delta: List[float],
        fallback_target: List[int],
        factor: float
    ) -> Optional[List[int]]:
        """Applica il delta alla box raw se presente, altrimenti scala verso il fallback_target."""
        if raw_box is not None:
            return [
                int(round(raw_box[i] + delta[i]))
                for i in range(4)
            ]
        elif factor > 0.1:
            return list(fallback_target)
        return None

    @staticmethod
    def _get_raw_at_time(
        t: float,
        raw_samples: List[Dict[str, Any]],
        subject: str
    ) -> Optional[List[int]]:
        """Trova il campione raw per il dato soggetto più vicino nel tempo."""
        if not raw_samples:
            return None
        best_dist = 999999.0
        best_sample = None
        for s in raw_samples:
            d = abs(s["t"] - t)
            if d < best_dist:
                best_dist = d
                best_sample = s
            elif d > best_dist:
                break
        return best_sample.get(subject) if best_sample else None
