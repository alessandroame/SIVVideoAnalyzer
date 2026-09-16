import pytest
from core.tracking.keyframe_manager import KeyframeManager


def test_ensure_raw_trajectory():
    tracking = {
        "trajectory": [
            {"t": 0.0, "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]},
            {"t": 1.0, "pilot": [105, 205, 50, 70], "wing": [85, 55, 120, 80]}
        ]
    }
    KeyframeManager.ensure_raw_trajectory(tracking)
    assert "raw_trajectory" in tracking
    assert len(tracking["raw_trajectory"]) == 2
    assert tracking["raw_trajectory"][0]["pilot"] == [100, 200, 50, 70]

    # Verifica che sia una copia indipendente
    tracking["trajectory"][0]["pilot"][0] = 999
    assert tracking["raw_trajectory"][0]["pilot"][0] == 100


def test_add_and_remove_keyframe():
    tracking = {
        "trajectory": [
            {"t": 0.0, "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]},
            {"t": 1.0, "pilot": [105, 205, 50, 70], "wing": [85, 55, 120, 80]},
            {"t": 2.0, "pilot": [110, 210, 50, 70], "wing": [90, 60, 120, 80]}
        ]
    }

    # Aggiungi keyframe per pilota a t=1.0 modificato a x=150
    KeyframeManager.add_keyframe(tracking, "pilot", 1.0, [150, 205, 50, 70])
    kfs = KeyframeManager.get_keyframes(tracking, "pilot")
    assert len(kfs) == 1
    assert kfs[0]["t"] == 1.0
    assert kfs[0]["box"] == [150, 205, 50, 70]

    # Verifica che la traiettoria sia stata ricalcolata
    assert tracking["trajectory"][1]["pilot"][0] == 150

    # Rimuovi keyframe
    removed = KeyframeManager.remove_keyframe(tracking, "pilot", 1.0)
    assert removed is True
    assert len(KeyframeManager.get_keyframes(tracking, "pilot")) == 0
    # La traiettoria deve essere tornata all'originale
    assert tracking["trajectory"][1]["pilot"][0] == 105


def test_multi_keyframe_smoothstep_interpolation():
    # Traiettoria lineare con pilota a x = 100, 100, 100...
    samples = [
        {"t": round(i * 0.5, 2), "pilot": [100, 200, 50, 70], "wing": [50, 50, 100, 80]}
        for i in range(11)  # t da 0.0 a 5.0
    ]
    tracking = {"trajectory": samples}

    # Imposta un keyframe a t=1.0 con offset +40 (x=140)
    # Imposta un secondo keyframe a t=3.0 con offset +80 (x=180)
    KeyframeManager.add_keyframe(tracking, "pilot", 1.0, [140, 200, 50, 70])
    KeyframeManager.add_keyframe(tracking, "pilot", 3.0, [180, 200, 50, 70])

    traj = tracking["trajectory"]
    # A t=1.0 x deve essere 140
    p_1_0 = [s["pilot"] for s in traj if s["t"] == 1.0][0]
    assert p_1_0[0] == 140

    # A t=3.0 x deve essere 180
    p_3_0 = [s["pilot"] for s in traj if s["t"] == 3.0][0]
    assert p_3_0[0] == 180

    # A t=2.0 (esattamente a metà, w=0.5, s=0.5), delta = (40 + 80)/2 = 60 -> x = 160
    p_2_0 = [s["pilot"] for s in traj if s["t"] == 2.0][0]
    assert p_2_0[0] == 160


def test_reset_keyframes():
    tracking = {
        "trajectory": [
            {"t": 0.0, "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]},
            {"t": 1.0, "pilot": [105, 205, 50, 70], "wing": [85, 55, 120, 80]}
        ]
    }
    KeyframeManager.add_keyframe(tracking, "wing", 0.0, [200, 50, 120, 80])
    assert tracking["trajectory"][0]["wing"][0] == 200

    KeyframeManager.reset_keyframes(tracking)
    assert tracking["trajectory"][0]["wing"][0] == 80
    assert len(KeyframeManager.get_keyframes(tracking, "wing")) == 0


def test_sidecar_keyframe_integration(tmp_path):
    from core.sidecar_manager import SidecarData
    mock_video = tmp_path / "flight.mp4"
    mock_video.touch()

    sidecar = SidecarData(str(mock_video))
    sidecar.tracking = {
        "trajectory": [
            {"t": 0.0, "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]},
            {"t": 1.0, "pilot": [105, 205, 50, 70], "wing": [85, 55, 120, 80]},
            {"t": 2.0, "pilot": [110, 210, 50, 70], "wing": [90, 60, 120, 80]}
        ]
    }
    sidecar.save()

    # Aggiungi keyframe tramite SidecarData
    sidecar.add_tracking_keyframe("pilot", 1.0, [150, 205, 50, 70])
    p_box, w_box = sidecar.get_tracking_boxes_at(1.0)
    assert p_box[0] == 150

    # Ricarica da disco
    sidecar_reloaded = SidecarData(str(mock_video))
    kfs = sidecar_reloaded.get_tracking_keyframes("pilot")
    assert len(kfs) == 1
    assert kfs[0]["box"][0] == 150

    # Ripristina originale
    sidecar_reloaded.reset_tracking_keyframes()
    p_box_restored, _ = sidecar_reloaded.get_tracking_boxes_at(1.0)
    assert p_box_restored[0] == 105
