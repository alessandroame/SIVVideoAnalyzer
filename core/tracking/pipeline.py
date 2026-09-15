import os
import time
from typing import Dict, Any, Optional, Callable, List
import numpy as np

from core.tracking.wing_tracker import WingTracker, WingBox
from core.tracking.pilot_tracker import PilotTracker, PilotBox
from core.tracking.smoother import TrajectorySmoother


class VideoTrackingPipeline:
    """
    Pipeline di analisi video per il tracciamento di Pilota e Vela.
    Elabora la clip con PyAV a step temporali regolari e produce
    la traiettoria stabilizzata da salvare nel file sidecar .json.
    """
    def __init__(
        self,
        sample_interval: float = 0.35,
        onnx_model_path: Optional[str] = None
    ):
        self.sample_interval = sample_interval
        self.wing_tracker = WingTracker(padding_ratio=0.15)
        self.pilot_tracker = PilotTracker(onnx_model_path=onnx_model_path)
        self.smoother = TrajectorySmoother(alpha=0.35, velocity_boost=0.65)

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

        # Parametri video
        fps = float(stream.average_rate) if stream.average_rate else 25.0
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
            progress_callback(5, "Avvio scansione video...")

        frame_idx = 0
        last_progress_emit = time.time()

        for frame in container.decode(stream):
            if is_cancelled and is_cancelled():
                return None

            if frame_idx % frame_step == 0:
                t_sec = float(frame.pts * stream.time_base) if frame.pts else (frame_idx / fps)

                # Estrai array RGB uint8
                img_rgb = frame.to_ndarray(format="rgb24")

                # 1. Rileva Vela
                wing_box = self.wing_tracker.detect(img_rgb)
                if wing_box:
                    last_wing = wing_box

                # 2. Rileva Pilota
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
                if now - last_progress_emit >= 0.5:
                    last_progress_emit = now
                    pct = int(min(90, 5 + (frame_idx / max(1, total_frames)) * 85))
                    if progress_callback:
                        progress_callback(pct, f"Tracciamento {t_sec:.1f}s / {duration_sec:.1f}s...")

            frame_idx += 1

        if not raw_samples:
            return None

        if progress_callback:
            progress_callback(92, "Stabilizzazione cinematografica traiettorie...")

        # 3. Stabilizzazione traiettorie
        smoothed_trajectory = self.smoother.smooth_trajectory(raw_samples)

        if progress_callback:
            progress_callback(100, "Tracciamento completato!")

        return {
            "version": "1.0",
            "sample_interval": self.sample_interval,
            "duration": round(duration_sec, 2),
            "video_width": width,
            "video_height": height,
            "samples_count": len(smoothed_trajectory),
            "trajectory": smoothed_trajectory
        }
