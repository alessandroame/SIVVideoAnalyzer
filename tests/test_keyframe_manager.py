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


def test_isolated_keyframe_fade_in_and_fade_out():
    """Verifica che un keyframe isolato sfumi all'interno della finestra e lasci intatto il resto."""
    # Campioni ogni 0.5s da 0 a 20s con pilota costante a x=100
    samples = [
        {"t": round(i * 0.5, 2), "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]}
        for i in range(41)
    ]
    tracking = {"trajectory": samples}

    # Aggiungi keyframe a t=10.0 con pilota a x=300 e finestra di 2.0s
    KeyframeManager.add_keyframe(tracking, "pilot", 10.0, [300, 200, 50, 70], window=2.0)

    traj_dict = {s["t"]: s["pilot"][0] for s in tracking["trajectory"]}

    # Fuori dalla finestra [8.0, 12.0]: tracciamento AI grezzo al 100% (x=100)
    assert traj_dict[7.5] == 100
    assert traj_dict[8.0] == 100
    assert traj_dict[12.0] == 100
    assert traj_dict[12.5] == 100
    assert traj_dict[15.0] == 100

    # Al keyframe esatto (t=10.0): x=300
    assert traj_dict[10.0] == 300

    # Fade In (t=9.0): valore compreso tra 100 e 300
    assert 100 < traj_dict[9.0] < 300
    # Fade Out (t=11.0): valore compreso tra 100 e 300
    assert 100 < traj_dict[11.0] < 300
    # Simmetria del fade attorno al keyframe
    assert traj_dict[9.0] == traj_dict[11.0]


def test_recovered_tracking_not_polluted_by_previous_delta():
    """
    Risolve il bug segnalato dall'utente:
    Quando l'AI perde il pilota al secondo 10 e l'utente lo corregge,
    il recupero dell'AI al secondo 11 NON deve essere spinto fuori schermo da un delta errato.
    """
    samples = [
        # AI perde il pilota a t=10.0 (segnala x=100 invece di x=500)
        {"t": 10.0, "pilot": [100, 400, 50, 70], "wing": None},
        # AI recupera il pilota a t=11.0 (segnala x=505, corretto)
        {"t": 11.0, "pilot": [505, 400, 50, 70], "wing": None},
        # AI continua correttamente a t=13.0 (segnala x=515)
        {"t": 13.0, "pilot": [515, 400, 50, 70], "wing": None}
    ]
    tracking = {"trajectory": samples}

    # L'utente corregge il frame errato a t=10.0 impostando x=500 con finestra di 2.0s
    KeyframeManager.add_keyframe(tracking, "pilot", 10.0, [500, 400, 50, 70], window=2.0)

    traj_dict = {s["t"]: s["pilot"][0] for s in tracking["trajectory"]}

    # A t=10.0: deve essere esattamente 500
    assert traj_dict[10.0] == 500

    # A t=11.0 (a metà fade out verso il recupero dell'AI):
    # La nuova formula fonde kf (500) e recovered raw (505), risultando ~502-503.
    # Con il VECCHIO codice sommava il delta (+400), facendo schizzare x a ~760!
    assert 500 <= traj_dict[11.0] <= 505

    # A t=13.0 (fuori finestra di 2.0s): deve essere esattamente il tracciamento recuperato dall'AI (515)
    assert traj_dict[13.0] == 515


def test_distant_keyframes_do_not_interfere():
    """Keyframe a minuti diversi non devono alterare la traccia AI intermedia."""
    samples = [
        {"t": float(i), "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]}
        for i in range(60)  # 1 minuto
    ]
    tracking = {"trajectory": samples}

    # Keyframe 1 a t=5.0 (x=200), Keyframe 2 a t=45.0 (x=300) con finestra default 2.0s
    KeyframeManager.add_keyframe(tracking, "pilot", 5.0, [200, 200, 50, 70], window=2.0)
    KeyframeManager.add_keyframe(tracking, "pilot", 45.0, [300, 200, 50, 70], window=2.0)

    traj_dict = {s["t"]: s["pilot"][0] for s in tracking["trajectory"]}

    # Al keyframe 1 e 2
    assert traj_dict[5.0] == 200
    assert traj_dict[45.0] == 300

    # A t=25.0 (esattamente a metà, lontano da entrambi): deve essere 100% traccia grezza (100)
    assert traj_dict[25.0] == 100


def test_correction_intervals_and_window_configuration():
    """Verifica il calcolo degli intervalli di correzione per la timeline."""
    tracking = {
        "trajectory": [
            {"t": float(i), "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]}
            for i in range(30)
        ]
    }
    # Imposta finestra globale a 1.5s
    KeyframeManager.set_transition_window(tracking, 1.5)
    assert KeyframeManager.get_transition_window(tracking) == 1.5

    # Aggiungi keyframe a t=10.0
    KeyframeManager.add_keyframe(tracking, "pilot", 10.0, [150, 200, 50, 70])
    intervals = KeyframeManager.get_correction_intervals(tracking, "pilot")
    assert len(intervals) == 1
    assert intervals[0]["start"] == 8.5  # 10.0 - 1.5
    assert intervals[0]["end"] == 11.5    # 10.0 + 1.5
    assert intervals[0]["keyframes"] == [10.0]

