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


def test_trajectory_smoother_aggressive_on_sudden_motion():
    smoother = TrajectorySmoother(velocity_threshold=12.0, velocity_boost=1.0)

    # Frame 0: pilota a (100, 200)
    # Frame 1: salto improvviso a (160, 240) (movimento repentino di 72px)
    raw = [
        {"t": 0.00, "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]},
        {"t": 0.04, "pilot": [160, 240, 50, 70], "wing": [140, 90, 120, 80]}
    ]

    smoothed = smoother.smooth_trajectory(raw)
    assert len(smoothed) == 2
    # Con tracking aggressivo (eff_alpha = 1.0), il box scatta istantaneamente al target senza ritardo
    assert smoothed[1]["pilot"] == [160, 240, 50, 70]


def test_interpolate_boxes_at_frame_snap():
    trajectory = [
        {"t": 0.00, "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]},
        {"t": 0.04, "pilot": [115, 205, 50, 70], "wing": [95, 55, 120, 80]},
        {"t": 0.08, "pilot": [130, 210, 50, 70], "wing": [110, 60, 120, 80]},
    ]

    # Timestamp molto vicino al secondo frame (0.041s rispetto a 0.04s): snap al fotogramma esatto
    p_box, w_box = TrajectorySmoother.interpolate_boxes_at(trajectory, 0.041)
    assert p_box == [115, 205, 50, 70]

    # Timestamp intermedio (0.06s): interpolazione coerente
    p_box_mid, _ = TrajectorySmoother.interpolate_boxes_at(trajectory, 0.06)
    assert p_box_mid is not None
    assert 115 <= p_box_mid[0] <= 130


def test_pilot_tracker_off_axis_swing():
    pilot_tracker = PilotTracker()
    frame = np.full((600, 600, 3), [140, 180, 220], dtype=np.uint8)

    # Vela inclinata / sbandata a sinistra
    wing_box = WingBox(x=150, y=50, w=150, h=80, confidence=0.85, pixel_count=2500)

    # Pilota sbandato fortemente a destra (fuori dal vecchio asse pendolare stretto, es. x=310, y=220)
    frame[210:240, 300:325] = [25, 25, 30]

    p_box = pilot_tracker.detect(frame, wing_box=wing_box)
    assert p_box is not None
    assert isinstance(p_box, PilotBox)
    # Deve rilevare il pilota sbandato senza fallire
    assert p_box.center_x > wing_box.center_x + 30


def test_dark_core_and_anatomical_box():
    pilot_tracker = PilotTracker()
    # Sfondo cielo/lago realistico a luminanza ~110
    frame = np.full((500, 500, 3), [110, 110, 110], dtype=np.uint8)

    # Vela a x=200, y=50, w=120, h=80
    wing_box = WingBox(x=200, y=50, w=120, h=80, confidence=0.85, pixel_count=3000)

    # Inserisci disturbo chiaro (riflesso sole / onda bianca / nuvola) a luminanza 190
    frame[160:190, 230:260] = [190, 190, 190]

    # Inserisci nucleo scuro del pilota (imbrago nero/antracite) a y=200, x=245..265
    frame[195:215, 245:265] = [35, 38, 42]

    p_box = pilot_tracker.detect(frame, wing_box=wing_box)
    assert p_box is not None
    assert isinstance(p_box, PilotBox)

    # Il tracker DEVE ignorare il riflesso chiaro a 190 e agganciare il Dark Core a 35!
    assert 220 <= p_box.center_x <= 280
    assert 160 <= p_box.center_y <= 240

    # Verifica vincolo anatomico per braccia e gambe:
    # Rapporto altezza / larghezza tra 1.20 e 1.60
    aspect_ratio = p_box.h / p_box.w
    assert 1.20 <= aspect_ratio <= 1.60

    # Verifica che il box si estenda sufficientemente verso l'alto (braccia/comandi)
    # e verso il basso (gambe/scarponi) attorno al centroide scuro (y~205)
    assert p_box.y < 205  # braccia sopra
    assert p_box.y + p_box.h > 215  # gambe sotto


def test_trajectory_smoother_dimension_stabilization():
    smoother = TrajectorySmoother(alpha=0.35, alpha_size=0.25, velocity_boost=0.85, velocity_threshold=20.0)

    # Simula micro-jitter nelle dimensioni rilevate (breathing del contorno)
    raw = [
        {"t": 0.00, "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]},
        {"t": 0.04, "pilot": [102, 201, 56, 76], "wing": [82, 51, 126, 84]},  # scatto di +6px in w, h
        {"t": 0.08, "pilot": [103, 202, 48, 68], "wing": [83, 52, 118, 78]}   # scatto di -8px in w, h
    ]

    smoothed = smoother.smooth_trajectory(raw)
    assert len(smoothed) == 3

    # Il frame 1 non deve saltare a w=56, h=76, ma deve essere stabilizzato dolcemente
    p1 = smoothed[1]["pilot"]
    assert p1 is not None
    assert 51 <= p1[2] <= 53  # larghezza stabilizzata
    assert 71 <= p1[3] <= 73  # altezza stabilizzata
