import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtMultimedia import QMediaPlayer

from ui.components.debriefing_player import DebriefingPlayerWidget
from ui.components.flight_table import FlightTableWidget
from ui.workers import AnalysisWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_player_arrow_nav_in_pause(qapp):
    player = DebriefingPlayerWidget()
    player._fps = 25.0  # 40ms per frame
    player.slider.setRange(0, 60000)

    # Assicuriamo che lo stato sia in PAUSE
    assert player.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState

    # Mock media_player position e _scrub_worker
    player.media_player.position = MagicMock(return_value=1000)
    player.media_player.setPosition = MagicMock()
    player._scrub_worker = MagicMock()

    # Step forward (+1 frame = +40ms)
    player.handle_arrow_nav(1)
    player.media_player.setPosition.assert_called_with(1040)
    player._scrub_worker.request_frame.assert_called_with(1040)
    assert player.slider.value() == 1040

    # Step backward (-1 frame = -40ms from 1040)
    player.media_player.position = MagicMock(return_value=1040)
    player.handle_arrow_nav(-1)
    player.media_player.setPosition.assert_called_with(1000)
    player._scrub_worker.request_frame.assert_called_with(1000)
    assert player.slider.value() == 1000


def test_player_arrow_nav_in_play(qapp):
    player = DebriefingPlayerWidget()
    player._fps = 50.0  # 20ms per frame
    player.slider.setRange(0, 60000)

    # Mock stato PLAYING
    player.media_player.playbackState = MagicMock(return_value=QMediaPlayer.PlaybackState.PlayingState)
    player.media_player.position = MagicMock(return_value=10000)
    player.media_player.setPosition = MagicMock()

    # Forward in play -> +5000ms
    player.handle_arrow_nav(1)
    player.media_player.setPosition.assert_called_with(15000)

    # Backward in play -> -5000ms
    player.media_player.position = MagicMock(return_value=15000)
    player.handle_arrow_nav(-1)
    player.media_player.setPosition.assert_called_with(10000)


def test_flight_table_tracking_badge(qapp):
    table_widget = FlightTableWidget()
    assert hasattr(table_widget, "lbl_badge_track")
    assert "Tracking: 0/0" in table_widget.lbl_badge_track.text()

    # Test chiamata a 4 argomenti (retrocompatibilità)
    table_widget.update_phases_status(2, 2, 1, 4)
    assert "Audio: 2/4" in table_widget.lbl_badge_audio.text()
    assert "Vela: 2/4" in table_widget.lbl_badge_wing.text()
    assert "Manovre: 1/4" in table_widget.lbl_badge_man.text()
    assert "Tracking: 0/4" in table_widget.lbl_badge_track.text()

    # Test chiamata a 5 argomenti (con tracking completato)
    table_widget.update_phases_status(4, 4, 4, 3, 4)
    assert "Tracking: 3/4" in table_widget.lbl_badge_track.text()

    # Completamento tracking al 100%
    table_widget.update_phases_status(4, 4, 4, 4, 4)
    assert "Tracking: 4/4" in table_widget.lbl_badge_track.text()
    assert "#10b981" in table_widget.lbl_badge_track.styleSheet()


def test_analysis_worker_phases_status_signal(qapp):
    worker = AnalysisWorker(
        video_files=["test1.mp4", "test2.mp4"],
        pilot_names=["Mario Rossi"],
        transcriber=MagicMock(),
        maneuver_detector=MagicMock()
    )

    received_phases = []
    worker.phases_status.connect(lambda a, w, m, trk, tot: received_phases.append((a, w, m, trk, tot)))

    # Emetti segnale con 5 parametri
    worker.phases_status.emit(2, 2, 2, 1, 2)
    assert received_phases == [(2, 2, 2, 1, 2)]


def test_flight_table_six_columns_and_status_widget(qapp, tmp_path):
    from PyQt6.QtWidgets import QHeaderView
    from ui.components.processing_status_widget import ProcessingStatusWidget

    table = FlightTableWidget()
    assert table.table_flights.columnCount() == 6

    # Verifica etichette delle intestazioni
    headers = [table.table_flights.horizontalHeaderItem(c).text() for c in range(6)]
    assert headers == ["File Video", "Data e Ora", "Volo N°", "Pilota Assegnato", "Stato Elaborazione", "Debriefing"]

    # Verifica che SOLO la Colonna 4 sia in modalità Stretch
    header = table.table_flights.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(3) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(4) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(5) == QHeaderView.ResizeMode.Interactive

    # Crea un file finto e aggiungi una riga
    v_file = str(tmp_path / "flight_test.mp4")
    with open(v_file, "w") as f:
        f.write("dummy")

    table.add_flight_row(
        video_path=v_file,
        pilot="Mario Rossi",
        flight_num=1,
        glider="Ozone Enzo",
        phrases="",
        is_confirmed=False
    )

    assert table.table_flights.rowCount() == 1
    cell_w = table.table_flights.cellWidget(0, 4)
    assert isinstance(cell_w, ProcessingStatusWidget)
    assert "In coda" in cell_w.lbl_status.text()

    # Test aggiornamento progresso clip (Fase 1)
    table.update_clip_progress(v_file, 15.0, 30.0)
    assert "50%" in cell_w.lbl_status.text()
    assert not cell_w.progress_bar.isHidden()

    # Test completamento identificazione pilota
    table.update_audio_result(v_file, 0.85, "Radio check", "Mario Rossi")
    assert "Radio 85%" in cell_w.lbl_status.text()

    # Test aggiornamento progresso manovre (Fase 2)
    table.update_maneuver_progress(v_file, "Ascolto comandi", 50)
    assert "50%" in cell_w.lbl_status.text()

