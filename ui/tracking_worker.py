from PyQt6.QtCore import QThread, pyqtSignal
from typing import Optional, Dict, Any

from core.tracking.pipeline import VideoTrackingPipeline
from core.sidecar_manager import SidecarData


class TrackingWorker(QThread):
    """
    Worker asincrono (QThread) per l'elaborazione del tracciamento di Pilota e Vela
    in background senza bloccare l'interfaccia grafica.
    """
    progress = pyqtSignal(int, str)             # percent (0..100), status message
    finished = pyqtSignal(str, dict)            # video_path, tracking_dict
    error = pyqtSignal(str, str)                # video_path, error_message

    def __init__(self, video_path: str, sample_interval: float = 0.20, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.sample_interval = sample_interval
        self._is_cancelled = False
        self.pipeline = VideoTrackingPipeline(sample_interval=self.sample_interval)

    def cancel(self):
        """Richiede l'annullamento dell'elaborazione."""
        self._is_cancelled = True

    def run(self):
        try:
            def on_progress(pct: int, msg: str):
                self.progress.emit(pct, msg)

            def is_cancelled() -> bool:
                return self._is_cancelled

            tracking_result = self.pipeline.process_video(
                video_path=self.video_path,
                progress_callback=on_progress,
                is_cancelled=is_cancelled
            )

            if self._is_cancelled:
                return

            if tracking_result:
                # Salva automaticamente nel sidecar portatile
                sidecar = SidecarData(self.video_path)
                sidecar.tracking = tracking_result
                sidecar.save()

                self.finished.emit(self.video_path, tracking_result)
            else:
                self.error.emit(self.video_path, "Nessun dato di tracciamento estratto.")

        except Exception as e:
            self.error.emit(self.video_path, str(e))
