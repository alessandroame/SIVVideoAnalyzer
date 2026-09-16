import os
import pytest
import numpy as np

from core.tracking.wing_tracker import WingTracker, WingBox
from core.tracking.pilot_tracker import PilotTracker, PilotBox
from core.tracking.smoother import TrajectorySmoother
from core.tracking.pipeline import VideoTrackingPipeline
from core.sidecar_manager import SidecarData


def test_wing_tracker_synthetic():
    tracker = WingTracker(padding_ratio=0.10, min_pixel_threshold=20)
    # Crea un frame sintetico 200x300 con cielo azzurro di sfondo
    # Cielo: R=150, G=190, B=230
    frame = np.full((200, 300, 3), [150, 190, 230], dtype=np.uint8)

    # Inserisci una vela rossa e gialla al centro superiore (y: 30..70, x: 100..200)
    frame[30:70, 100:150] = [255, 30, 30]    # Rosso saturo
    frame[30:70, 150:200] = [255, 230, 20]   # Giallo saturo

    box = tracker.detect(frame)
    assert box is not None
    assert isinstance(box, WingBox)
    assert box.w > 80
    assert box.h > 30
    assert box.confidence > 0.3
    assert 90 <= box.center_x <= 210


def test_pilot_tracker_pendulum_constraint():
    pilot_tracker = PilotTracker()

    # Frame 400x400
    frame = np.full((400, 400, 3), [140, 180, 220], dtype=np.uint8)

    # Vela a x: 150, y: 50, w: 100, h: 60
    wing_box = WingBox(x=150, y=50, w=100, h=60, confidence=0.85, pixel_count=2000)

    # Inserisci contrasto pilota sotto la vela (es. imbrago nero a y=160, x=190..210)
    frame[150:180, 190:210] = [20, 25, 30]

    p_box = pilot_tracker.detect(frame, wing_box=wing_box)
    assert p_box is not None
    assert isinstance(p_box, PilotBox)
    # Il pilota deve trovarsi sotto la vela
    assert p_box.y >= wing_box.y + wing_box.h - 15
    # Il centro X del pilota deve essere allineato al centro della vela
    assert abs(p_box.center_x - wing_box.center_x) < 40


def test_pilot_tracker_fallback():
    pilot_tracker = PilotTracker()
    frame = np.zeros((300, 300, 3), dtype=np.uint8)

    last_box = PilotBox(x=100, y=120, w=40, h=60, confidence=0.8)
    p_box = pilot_tracker.detect(frame, wing_box=None, last_pilot_box=last_box)

    assert p_box is not None
    assert p_box.x == last_box.x
    assert p_box.y == last_box.y
    assert p_box.confidence < last_box.confidence


def test_trajectory_smoother():
    smoother = TrajectorySmoother(alpha=0.3)

    raw = [
        {"t": 0.0, "pilot": [100, 200, 40, 60], "wing": [80, 50, 120, 80]},
        {"t": 0.5, "pilot": [102, 201, 40, 60], "wing": [82, 51, 120, 80]},
        {"t": 1.0, "pilot": [104, 202, 40, 60], "wing": [84, 52, 120, 80]}
    ]

    smoothed = smoother.smooth_trajectory(raw)
    assert len(smoothed) == 3
    assert smoothed[0]["t"] == 0.0
    assert smoothed[1]["pilot"] is not None

    # Test interpolazione
    p_interp, w_interp = TrajectorySmoother.interpolate_boxes_at(smoothed, 0.25)
    assert p_interp is not None
    assert w_interp is not None
    assert 100 <= p_interp[0] <= 104


def test_sidecar_tracking_integration(tmp_path):
    mock_video = tmp_path / "test_siv.mp4"
    mock_video.touch()

    sidecar = SidecarData(str(mock_video))
    assert not sidecar.has_tracking()

    tracking_payload = {
        "version": "1.0",
        "sample_interval": 0.35,
        "duration": 10.0,
        "video_width": 1920,
        "video_height": 1080,
        "trajectory": [
            {"t": 0.0, "pilot": [500, 600, 100, 150], "wing": [400, 200, 300, 200]},
            {"t": 2.0, "pilot": [520, 610, 100, 150], "wing": [420, 210, 300, 200]}
        ]
    }

    sidecar.tracking = tracking_payload
    sidecar.save()

    # Ricarica da disco
    sidecar_reloaded = SidecarData(str(mock_video))
    assert sidecar_reloaded.has_tracking()
    p_box, w_box = sidecar_reloaded.get_tracking_boxes_at(1.0)
    assert p_box is not None
    assert w_box is not None
    assert p_box == [510, 605, 100, 150]


def test_real_video_frame_detection():
    real_video = "output_siv/alessandro/00311.mp4"
    if not os.path.exists(real_video):
        pytest.skip("File video di test non disponibile nell'ambiente.")

    import av
    container = av.open(real_video)
    stream = container.streams.video[0]
    pts = int(30.0 / stream.time_base)
    container.seek(pts, any_frame=False, stream=stream)

    tracker = WingTracker()
    pilot_tracker = PilotTracker()

    for frame in container.decode(stream):
        img = frame.to_ndarray(format="rgb24")
        wing_box = tracker.detect(img)
        assert wing_box is not None
        assert wing_box.w > 100
        assert wing_box.h > 50

        pilot_box = pilot_tracker.detect(img, wing_box=wing_box)
        assert pilot_box is not None
        assert pilot_box.y >= wing_box.y
        break


def test_pipeline_on_real_sample_video():
    video_path = "temp/test_deinterlace.mp4"
    if not os.path.exists(video_path):
        pytest.skip("temp/test_deinterlace.mp4 non disponibile")

    pipeline = VideoTrackingPipeline(sample_interval=0.20)
    res = pipeline.process_video(video_path)

    assert res is not None
    assert res["version"] == "2.0"
    assert res["samples_count"] > 15
    assert len(res["trajectory"]) > 15

    # Verifica che la vela e il pilota siano tracciati
    valid_wings = [s for s in res["trajectory"] if s["wing"] is not None]
    valid_pilots = [s for s in res["trajectory"] if s["pilot"] is not None]

    assert len(valid_wings) > 10
    assert len(valid_pilots) > 10

    # Verifica dimensioni ragionevoli dei box
    first_w = valid_wings[0]["wing"]
    assert first_w[2] > 30 and first_w[3] > 20

