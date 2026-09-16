import os
import time
from typing import Dict, Any, Optional, Callable, List
import numpy as np

from core.tracking.wing_tracker import WingTracker, WingBox
from core.tracking.pilot_tracker import PilotTracker, PilotBox
from core.tracking.smoother import TrajectorySmoother


class VideoTrackingPipeline:
    """
    Pipeline di analisi video ad alta precisione per il tracciamento di Pilota e Vela.
    Elabora la clip video ad alta frequenza (predefinito 0.04s / 25 fps, fotogramma per fotogramma),
    applica blob detection adattiva e vincoli pendolari SIV, e produce la traiettoria
    stabilizzata e reattiva salvata nel sidecar .json.
    """
    def __init__(
        self,
        sample_interval: float = 0.04,
        onnx_model_path: Optional[str] = None
    ):
        self.sample_interval = sample_interval
        self.wing_tracker = WingTracker(padding_ratio=0.12)
        self.pilot_tracker = PilotTracker(onnx_model_path=onnx_model_path)
        self.smoother = TrajectorySmoother(alpha=0.35, alpha_size=0.25, velocity_boost=0.85, velocity_threshold=20.0)

    def process_video(
        self,
        video_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Esegue la scansione completa della clip video.
        Ritorna il dizionario pronto per il salvataggio in SidecarData["tracking"].
        """
        if not os.path.exists(video_path):
            return None

        import av

        try:
            container = av.open(video_path)
            stream = container.streams.video[0]
        except Exception as e:
            if progress_callback:
                progress_callback(0, f"Errore apertura video: {e}")
            return None

        # Prova a leggere i colori della vela dal sidecar per raffinare la rilevazione
        try:
            from core.sidecar_manager import SidecarData
            sidecar = SidecarData(video_path)
            if sidecar.glider:
                # Esempio: "Ozone Rush - Rosso / Bianco"
                parts = sidecar.glider.replace("-", ",").replace("/", ",").split(",")
                colors = [p.strip() for p in parts if p.strip()]
                if colors:
                    self.wing_tracker.set_target_colors(colors)
        except Exception:
            pass

        # Parametri video
        fps = float(stream.average_rate) if stream.average_rate else 25.0
        if self.sample_interval <= 0.04:
            # Modalità aggressiva fotogramma per fotogramma per framerate standard (24-32 fps)
            frame_step = 1 if fps <= 32.0 else max(1, int(round(fps * self.sample_interval)))
        else:
            frame_step = max(1, int(round(fps * self.sample_interval)))
        width = stream.width
        height = stream.height

        duration_sec = 0.0
        if stream.duration and stream.time_base:
            duration_sec = float(stream.duration * stream.time_base)
        else:
            from core.audio_extractor import get_video_duration
            duration_sec = get_video_duration(video_path)

        total_frames = int(stream.frames) if stream.frames else int(duration_sec * fps)

        raw_samples: List[Dict[str, Any]] = []
        last_pilot: Optional[PilotBox] = None
        last_wing: Optional[WingBox] = None

        if progress_callback:
            progress_callback(5, "Avvio scansione video ad alta precisione...")

        frame_idx = 0
        last_progress_emit = time.time()

        for frame in container.decode(stream):
            if is_cancelled and is_cancelled():
                return None

            if frame_idx % frame_step == 0:
                t_sec = float(frame.pts * stream.time_base) if frame.pts else (frame_idx / fps)

                # Estrai array RGB uint8
                img_rgb = frame.to_ndarray(format="rgb24")

                # 1. Rileva Vela con memoria temporale
                wing_box = self.wing_tracker.detect(img_rgb, last_wing_box=last_wing)
                if wing_box:
                    last_wing = wing_box

                # 2. Rileva Pilota nel cono pendolare sotto la vela
                pilot_box = self.pilot_tracker.detect(
                    img_rgb=img_rgb,
                    wing_box=wing_box or last_wing,
                    last_pilot_box=last_pilot
                )
                if pilot_box:
                    last_pilot = pilot_box

                raw_samples.append({
                    "t": round(t_sec, 3),
                    "pilot": pilot_box.to_list() if pilot_box else None,
                    "wing": wing_box.to_list() if wing_box else None
                })

                # Notifica progresso periodico (max 2 volte al secondo)
                now = time.time()
                if now - last_progress_emit >= 0.4:
                    last_progress_emit = now
                    pct = int(min(90, 5 + (frame_idx / max(1, total_frames)) * 85))
                    if progress_callback:
                        progress_callback(pct, f"Tracciamento {t_sec:.1f}s / {duration_sec:.1f}s...")

            frame_idx += 1

        if not raw_samples:
            return None

        if progress_callback:
            progress_callback(92, "Stabilizzazione cinematografica traiettorie...")

        # 3. Stabilizzazione cinematografica con outlier rejection
        smoothed_trajectory = self.smoother.smooth_trajectory(raw_samples)

        if progress_callback:
            progress_callback(100, "Tracciamento completato con successo!")

        return {
            "version": "2.0",
            "sample_interval": self.sample_interval,
            "duration": round(duration_sec, 2),
            "video_width": width,
            "video_height": height,
            "samples_count": len(smoothed_trajectory),
            "trajectory": smoothed_trajectory
        }
