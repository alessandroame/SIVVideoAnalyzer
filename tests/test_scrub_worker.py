import time
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage
from ui.scrub_worker import ScrubWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_scrub_worker_valid_video(qapp):
    worker = ScrubWorker("temp/bench_yadif.mp4")
    frames = []
    worker.frame_ready.connect(lambda img, s: frames.append((img, s)))
    worker.start()

    # Request a frame at 3.0 seconds (3000 ms)
    worker.request_frame(3000)

    # Wait up to 3.0 seconds for frame_ready
    t0 = time.time()
    while len(frames) == 0 and time.time() - t0 < 3.0:
        qapp.processEvents()
        time.sleep(0.02)

    worker.stop()

    assert len(frames) >= 1
    qimg, s = frames[0]
    assert isinstance(qimg, QImage)
    assert not qimg.isNull()
    assert qimg.width() == 1920
    assert qimg.height() == 1080
    assert abs(s - 3.0) < 0.5


def test_scrub_worker_invalid_video(qapp):
    worker = ScrubWorker("non_existent_video_path.mp4")
    frames = []
    worker.frame_ready.connect(lambda img, s: frames.append((img, s)))
    worker.start()
    worker.request_frame(1000)
    time.sleep(0.1)
    qapp.processEvents()
    worker.stop()
    assert len(frames) == 0
