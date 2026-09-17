from typing import Dict, Any, List, Optional, Tuple


class KeyframeManager:
    """
    Gestore della correzione interattiva delle traiettorie tramite Keyframe.
    Supporta:
    - Architettura non distruttiva (conservazione di 'raw_trajectory')
    - Position Alpha-Blending con curva cubica Hermite / Smoothstep (3w^2 - 2w^3):
      le correzioni sfumano dolcemente dal tracciamento AI (Fade In) ed escono
      ricongiungendosi naturalmente al tracciamento AI recuperato (Fade Out)
    - Finestra di transizione e correzione configurabile (default 2.0s)
    - Isolamento temporale: i frame al di fuori della finestra di correzione
      rimangono inalterati al 100%
    - Interpolazione diretta multi-keyframe per cluster ravvicinati
    - Ripristino istantaneo al tracciamento grezzo AI
    """

    DEFAULT_TRANSITION_WINDOW = 2.0  # Durata predefinita (secondi) della finestra di fade in/out

    @staticmethod
    def ensure_raw_trajectory(tracking_dict: Dict[str, Any]) -> None:
        """Assicura che esista una copia immutabile della traiettoria grezza AI."""
        if "raw_trajectory" not in tracking_dict or not tracking_dict["raw_trajectory"]:
            current_traj = tracking_dict.get("trajectory", [])
            tracking_dict["raw_trajectory"] = [
                {
                    "t": s.get("t", 0.0),
                    "pilot": list(s["pilot"]) if s.get("pilot") else None,
                    "wing": list(s["wing"]) if s.get("wing") else None
                }
                for s in current_traj
            ]

    @classmethod
    def get_transition_window(cls, tracking_dict: Dict[str, Any]) -> float:
        """Restituisce la durata della finestra di transizione configurata o il default."""
        return float(tracking_dict.get("transition_window", cls.DEFAULT_TRANSITION_WINDOW))

    @classmethod
    def set_transition_window(cls, tracking_dict: Dict[str, Any], window: float) -> None:
        """Imposta la durata della finestra di transizione e ricalcola la traiettoria."""
        valid_win = max(0.2, min(15.0, float(window)))
        tracking_dict["transition_window"] = round(valid_win, 2)
        cls.recalculate_trajectory(tracking_dict, transition_window=valid_win)

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
        window: Optional[float] = None,
        transition_window: Optional[float] = None
    ) -> None:
        """
        Aggiunge o aggiorna un keyframe per il soggetto ('pilot' o 'wing') al tempo t.
        Ricalcola immediatamente la traiettoria 'trajectory' con fade in/out localizzato.
        """
        if subject not in ("pilot", "wing"):
            raise ValueError(f"Soggetto non valido: {subject}. Atteso 'pilot' o 'wing'.")

        cls.ensure_raw_trajectory(tracking_dict)
        kfs = cls.get_keyframes(tracking_dict)
        subj_kfs = kfs.setdefault(subject, [])

        t_rounded = round(float(t), 3)
        clean_box = [int(round(v)) for v in box[:4]]
        eff_win = cls.get_transition_window(tracking_dict) if transition_window is None else transition_window

        # Controlla se esiste già un keyframe vicino (entro 0.05s) per aggiornarlo
        updated = False
        for kf in subj_kfs:
            if abs(kf.get("t", 0.0) - t_rounded) <= 0.05:
                kf["t"] = t_rounded
                kf["box"] = clean_box
                if window is not None:
                    kf["window"] = round(float(window), 2)
                updated = True
                break

        if not updated:
            kf_entry: Dict[str, Any] = {"t": t_rounded, "box": clean_box}
            if window is not None:
                kf_entry["window"] = round(float(window), 2)
            subj_kfs.append(kf_entry)

        # Ordina i keyframe temporalmente
        subj_kfs.sort(key=lambda k: k.get("t", 0.0))

        # Ricalcola la traiettoria
        cls.recalculate_trajectory(tracking_dict, transition_window=eff_win)

    @classmethod
    def remove_keyframe(
        cls,
        tracking_dict: Dict[str, Any],
        subject: str,
        t: float,
        tolerance: float = 0.35,
        transition_window: Optional[float] = None
    ) -> bool:
        """Rimuove il keyframe più vicino a t (entro la tolleranza)."""
        kfs = cls.get_keyframes(tracking_dict)
        subj_kfs = kfs.get(subject, [])
        if not subj_kfs:
            return False

        original_len = len(subj_kfs)
        kfs[subject] = [kf for kf in subj_kfs if abs(kf.get("t", 0.0) - t) > tolerance]

        if len(kfs[subject]) < original_len:
            eff_win = cls.get_transition_window(tracking_dict) if transition_window is None else transition_window
            cls.recalculate_trajectory(tracking_dict, transition_window=eff_win)
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
        transition_window: Optional[float] = None
    ) -> None:
        """
        Ricalcola la lista 'trajectory' integrando 'raw_trajectory' con i keyframe manuali.
        Utilizza un'interpolazione position-blending con sfumatura smoothstep (Hermite cubic).
        """
        cls.ensure_raw_trajectory(tracking_dict)
        raw_samples = tracking_dict.get("raw_trajectory", [])
        if not raw_samples:
            return

        keyframes_all = cls.get_keyframes(tracking_dict)
        pilot_kfs = keyframes_all.get("pilot", [])
        wing_kfs = keyframes_all.get("wing", [])

        # Se non ci sono keyframe, la traiettoria coincide con la grezza
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

        win = cls.get_transition_window(tracking_dict) if transition_window is None else transition_window
        new_trajectory = []

        for sample in raw_samples:
            t = sample["t"]
            raw_p = sample.get("pilot")
            raw_w = sample.get("wing")

            corr_p = cls._calculate_subject_box_at(
                t=t,
                raw_box=raw_p,
                keyframes=pilot_kfs,
                default_window=win
            )

            corr_w = cls._calculate_subject_box_at(
                t=t,
                raw_box=raw_w,
                keyframes=wing_kfs,
                default_window=win
            )

            new_trajectory.append({
                "t": t,
                "pilot": corr_p,
                "wing": corr_w
            })

        tracking_dict["trajectory"] = new_trajectory

    @classmethod
    def get_correction_intervals(
        cls,
        tracking_dict: Dict[str, Any],
        subject: Optional[str] = None,
        default_window: Optional[float] = None
    ) -> Any:
        """
        Restituisce gli intervalli temporali in cui la correzione manuale è attiva o sfumata.
        Utile per disegnare sulla timeline le fasce evidenziate con le zone di fade.
        Formato per soggetto: [{'start': t_start, 'end': t_end, 'keyframes': [t1, t2, ...]}]
        """
        def_win = cls.get_transition_window(tracking_dict) if default_window is None else default_window
        kfs_all = cls.get_keyframes(tracking_dict)

        def _compute_for_subject(subj_name: str) -> List[Dict[str, Any]]:
            subj_kfs = kfs_all.get(subj_name, [])
            if not subj_kfs:
                return []

            intervals: List[Dict[str, Any]] = []
            cur_start = None
            cur_end = None
            cur_times: List[float] = []

            for kf in subj_kfs:
                t_kf = float(kf.get("t", 0.0))
                w_kf = float(kf.get("window", def_win))
                k_start = max(0.0, t_kf - w_kf)
                k_end = t_kf + w_kf

                if cur_start is None:
                    cur_start = k_start
                    cur_end = k_end
                    cur_times = [t_kf]
                elif k_start <= cur_end:
                    # Sovrapposizione o giunzione continua
                    cur_end = max(cur_end, k_end)
                    cur_times.append(t_kf)
                else:
                    intervals.append({
                        "start": round(cur_start, 2),
                        "end": round(cur_end, 2),
                        "keyframes": cur_times
                    })
                    cur_start = k_start
                    cur_end = k_end
                    cur_times = [t_kf]

            if cur_start is not None and cur_end is not None:
                intervals.append({
                    "start": round(cur_start, 2),
                    "end": round(cur_end, 2),
                    "keyframes": cur_times
                })

            return intervals

        if subject:
            return _compute_for_subject(subject)
        return {
            "pilot": _compute_for_subject("pilot"),
            "wing": _compute_for_subject("wing")
        }

    @classmethod
    def _calculate_subject_box_at(
        cls,
        t: float,
        raw_box: Optional[List[int]],
        keyframes: List[Dict[str, Any]],
        default_window: float
    ) -> Optional[List[int]]:
        """
        Calcola la box corretta per un soggetto a un dato timestamp t utilizzando
        position alpha-blending e fade in/out localizzato.
        """
        if not keyframes:
            return raw_box

        # Caso 1: t precede il primo keyframe
        if t <= keyframes[0]["t"]:
            kf0 = keyframes[0]
            t0 = kf0["t"]
            w0 = float(kf0.get("window", default_window))
            t_start = t0 - w0

            if t < t_start:
                # Fuori dalla finestra di correzione: traccia AI intatta
                return raw_box

            if t >= t0 - 1e-4:
                return list(kf0["box"])

            # Fade In graduale verso il primo keyframe
            ratio = (t - t_start) / max(1e-4, t0 - t_start)
            alpha = cls._smoothstep(ratio)
            return cls._blend_boxes(raw_box, kf0["box"], alpha)

        # Caso 2: t succede l'ultimo keyframe
        if t >= keyframes[-1]["t"]:
            kf_last = keyframes[-1]
            t_last = kf_last["t"]
            w_last = float(kf_last.get("window", default_window))
            t_end = t_last + w_last

            if t > t_end:
                # Fuori dalla finestra di correzione: traccia AI intatta
                return raw_box

            if t <= t_last + 1e-4:
                return list(kf_last["box"])

            # Fade Out graduale verso la traccia AI recuperata
            ratio = (t_end - t) / max(1e-4, t_end - t_last)
            alpha = cls._smoothstep(ratio)
            return cls._blend_boxes(raw_box, kf_last["box"], alpha)

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
        if abs(t - t_prev) < 1e-4:
            return list(kf_prev["box"])
        if abs(t - t_next) < 1e-4:
            return list(kf_next["box"])

        w_prev = float(kf_prev.get("window", default_window))
        w_next = float(kf_next.get("window", default_window))
        dt = max(1e-4, t_next - t_prev)

        # Verifica se i due keyframe appartengono allo stesso cluster di correzione
        # oppure se la distanza è sufficientemente ampia da separare le due finestre
        if dt <= (w_prev + w_next):
            # Cluster continuo: interpolazione diretta tra i due keyframe manuali (alpha = 1.0)
            # Immune da anomalie o perdite dell'AI nell'intervallo manuale
            w = max(0.0, min(1.0, (t - t_prev) / dt))
            s = cls._smoothstep(w)
            b_prev = kf_prev["box"]
            b_next = kf_next["box"]
            return [
                int(round((1.0 - s) * b_prev[j] + s * b_next[j]))
                for j in range(4)
            ]
        else:
            # Keyframe distanti: due correzioni separate con intervallo AI puro nel mezzo
            if t <= t_prev + w_prev:
                # Zona di Fade Out del keyframe precedente
                ratio = (t_prev + w_prev - t) / max(1e-4, w_prev)
                alpha = cls._smoothstep(ratio)
                return cls._blend_boxes(raw_box, kf_prev["box"], alpha)
            elif t >= t_next - w_next:
                # Zona di Fade In del keyframe successivo
                ratio = (t - (t_next - w_next)) / max(1e-4, w_next)
                alpha = cls._smoothstep(ratio)
                return cls._blend_boxes(raw_box, kf_next["box"], alpha)
            else:
                # Intervallo intermedio: tracciamento originale AI al 100%
                return raw_box

    @staticmethod
    def _smoothstep(x: float) -> float:
        """Curva cubica Hermite smoothstep 3x^2 - 2x^3 con accelerazione e decelerazione morbida."""
        clamped = max(0.0, min(1.0, x))
        return clamped * clamped * (3.0 - 2.0 * clamped)

    @staticmethod
    def _blend_boxes(
        raw_box: Optional[List[int]],
        kf_box: List[int],
        alpha: float
    ) -> Optional[List[int]]:
        """
        Fonde in modo graduale (alpha blending) la box raw con la box del keyframe.
        alpha = 0.0 -> 100% raw_box (tracciamento AI originale)
        alpha = 1.0 -> 100% kf_box (keyframe manuale)
        Se raw_box non è disponibile (bersaglio perso dall'AI), mantiene la box del keyframe
        finché alpha > 0.05 per evitare sparizioni o glitch.
        """
        if raw_box is None:
            if alpha > 0.05:
                return [int(round(v)) for v in kf_box[:4]]
            return None

        return [
            int(round((1.0 - alpha) * raw_box[j] + alpha * kf_box[j]))
            for j in range(4)
        ]
