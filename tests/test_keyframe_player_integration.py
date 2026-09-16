import pytest
from PyQt6.QtWidgets import QApplication
from ui.components.keyframe_bar import KeyframeBar
from ui.components.debriefing_player import DebriefingPlayerWidget
from core.sidecar_manager import SidecarData

@pytest.fixture(scope="module")
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_keyframe_bar_ui(app):
    bar = KeyframeBar()
    assert bar.active_subject == "pilot"

    # Cambia a vela
    bar.set_active_subject("wing")
    assert bar.active_subject == "wing"
    assert bar.btn_wing.isChecked()
    assert not bar.btn_pilot.isChecked()

    # Imposta keyframes
    bar.set_keyframes({
        "pilot": [{"t": 10.0, "box": [100, 200, 50, 70]}],
        "wing": [{"t": 15.0, "box": [80, 50, 120, 80]}]
    })
    assert "2 Keyframe" in bar.lbl_status.text()


def test_debriefing_player_keyframe_workflow(app, tmp_path):
    mock_video = tmp_path / "test_flight.mp4"
    mock_video.touch()

    # Prepara sidecar con tracking
    sidecar = SidecarData(str(mock_video))
    sidecar.tracking = {
        "trajectory": [
            {"t": 0.0, "pilot": [100, 200, 50, 70], "wing": [80, 50, 120, 80]},
            {"t": 2.0, "pilot": [104, 204, 50, 70], "wing": [84, 54, 120, 80]},
            {"t": 4.0, "pilot": [108, 208, 50, 70], "wing": [88, 58, 120, 80]}
        ]
    }
    sidecar.save()

    player = DebriefingPlayerWidget()
    player.open_video(str(mock_video), auto_calc_tracking=False)

    # Simula posizione a 2.0s (2000 ms)
    sim_pos = [2000]
    player.media_player.position = lambda: sim_pos[0]
    player.media_player.setPosition = lambda val: sim_pos.__setitem__(0, val)

    # 1. Simula modifica interattiva di un box
    player._on_box_drag_started()
    player._on_box_interactively_modified("pilot", [150, 204, 50, 70])

    # 2. Simula rilascio mouse (commit keyframe)
    player._on_keyframe_committed("pilot", [150, 204, 50, 70])

    # Verifica che il keyframe sia memorizzato
    kfs = player.current_sidecar.get_tracking_keyframes("pilot")
    assert len(kfs) == 1
    assert kfs[0]["box"][0] == 150

    # Verifica che la traiettoria sia stata corretta
    p_box, _ = player.current_sidecar.get_tracking_boxes_at(2.0)
    assert p_box[0] == 150

    # 3. Navigazione keyframe (prev / next)
    sim_pos[0] = 0
    player._on_next_keyframe()
    assert sim_pos[0] == 2000

    sim_pos[0] = 4000
    player._on_prev_keyframe()
    assert sim_pos[0] == 2000

    # 4. Eliminazione keyframe tramite _on_delete_keyframe
    player._on_delete_keyframe("pilot")
    assert len(player.current_sidecar.get_tracking_keyframes("pilot")) == 0
    p_box_restored, _ = player.current_sidecar.get_tracking_boxes_at(2.0)
    assert p_box_restored[0] == 104

    # 5. Aggiungi di nuovo un keyframe ed eliminalo con il clic destro simulato dallo slider
    player._on_keyframe_committed("pilot", [160, 204, 50, 70])
    assert len(player.current_sidecar.get_tracking_keyframes("pilot")) == 1
    # Trigger segnale di cancellazione da slider col tasto destro
    player._on_slider_keyframe_delete_requested("pilot", 2.0)
    assert len(player.current_sidecar.get_tracking_keyframes("pilot")) == 0

