import cv2
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker, QWaitCondition
from PyQt6.QtGui import QImage


class ScrubWorker(QThread):
    """Worker asincrono (QThread) per l'estrazione ultra-rapida di fotogrammi video

    durante lo scrubbing (trascinamento del cursore sulla timeline).
    Utilizza OpenCV in background per bypassare la latenza e i blocchi di seek
    della pipeline WMF/QtMultimedia, garantendo un'anteprima fluida in tempo reale.
    """
    frame_ready = pyqtSignal(QImage, float)   # (QImage del frame, tempo in secondi)

    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self._target_ms: Optional[int] = None
        self._running = True
        self._mutex = QMutex()
        self._condition = QWaitCondition()

    def request_frame(self, ms: int):
        """Richiede l'estrazione del fotogramma al millisecondo indicato."""
        with QMutexLocker(self._mutex):
            self._target_ms = ms
            self._condition.wakeOne()

    def run(self):
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0:
            fps = 25.0

        last_ms = -1
        while self._running:
            target = None
            with QMutexLocker(self._mutex):
                if self._target_ms is None or self._target_ms == last_ms:
                    self._condition.wait(self._mutex, 40)
                if not self._running:
                    break
                target = self._target_ms

            if target is not None and target != last_ms:
                last_ms = target
                frame_idx = max(0, int(round((target / 1000.0) * fps)))
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_MSEC, target)
                    ret, frame = cap.read()
                if ret and self._running:
                    h, w, _ = frame.shape
                    # Conversione rapida da BGR a RGB per QImage
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
                    self.frame_ready.emit(qimg, target / 1000.0)

        cap.release()

    def stop(self):
        """Ferma il worker e rilascia il decoder video OpenCV."""
        with QMutexLocker(self._mutex):
            self._running = False
            self._condition.wakeAll()
        self.wait(1000)
