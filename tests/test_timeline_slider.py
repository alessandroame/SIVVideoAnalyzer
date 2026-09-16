import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QRect, QPointF
from PyQt6.QtGui import QMouseEvent, QPainter, QPixmap, QKeyEvent

from ui.components.timeline_slider import SIVTimelineSlider


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_timeline_slider_init(qapp):
    slider = SIVTimelineSlider()
    slider.resize(400, 30)
    assert slider.orientation() == Qt.Orientation.Horizontal
    assert slider.is_dragging is False
    assert slider.minimum() == 0
    assert slider._chapters == []


def test_timeline_slider_set_chapters(qapp):
    slider = SIVTimelineSlider()
    chapters = [
        {"start": 10.5, "end": 25.0, "title": "Asimmetrica Destra"},
        {"start": 45.0, "end": 60.0, "title": "Stallo Completo"}
    ]
    slider.set_chapters(chapters)
    assert len(slider._chapters) == 2
    assert slider._chapters[0]["title"] == "Asimmetrica Destra"


def test_timeline_slider_pos_to_val_and_val_to_x(qapp):
    slider = SIVTimelineSlider()
    slider.resize(400, 30)
    slider.setRange(0, 100000)  # 100 seconds

    track = slider._get_track_rect()
    assert track.width() == 400 - 20  # margin = 10 -> 380px

    # Leftmost position
    assert slider._val_to_x(0, track) == track.left()
    # Rightmost position
    assert slider._val_to_x(100000, track) == track.right()
    # Midpoint
    mid_x = track.left() + track.width() // 2
    mid_val = slider._pos_to_val(mid_x)
    assert abs(mid_val - 50000) < 500


def test_timeline_slider_click_to_seek(qapp):
    slider = SIVTimelineSlider()
    slider.resize(400, 30)
    slider.setRange(0, 60000)  # 60 seconds

    seek_values = []
    slider.seek_requested.connect(seek_values.append)

    track = slider._get_track_rect()
    target_x = track.left() + int(track.width() * 0.5)

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(float(target_x), 15.0),
        QPointF(float(target_x), 15.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    slider.mousePressEvent(event)

    assert slider.is_dragging is True
    assert len(seek_values) == 1
    assert abs(seek_values[0] - 30000) < 500


def test_timeline_slider_snap_to_chapter(qapp):
    slider = SIVTimelineSlider()
    slider.resize(400, 30)
    slider.setRange(0, 100000)  # 100 seconds
    chapters = [
        {"start": 20.0, "end": 35.0, "title": "Frontale"}
    ]
    slider.set_chapters(chapters)

    seek_values = []
    slider.seek_requested.connect(seek_values.append)

    track = slider._get_track_rect()
    # 20.0 seconds = 20000 ms -> compute exact x
    ch_x = slider._val_to_x(20000, track)

    # Click 4 pixels away from chapter marker (within tolerance of 8px)
    click_x = ch_x + 4
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(float(click_x), 15.0),
        QPointF(float(click_x), 15.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    slider.mousePressEvent(event)

    # Should snap exactly to 20000 ms
    assert slider.value() == 20000
    assert seek_values[-1] == 20000


def test_timeline_slider_drag_throttling_and_release(qapp):
    slider = SIVTimelineSlider()
    slider.resize(400, 30)
    slider.setRange(0, 60000)

    seek_values = []
    drag_started_called = []
    drag_ended_called = []

    slider.seek_requested.connect(seek_values.append)
    slider.drag_started.connect(lambda: drag_started_called.append(True))
    slider.drag_ended.connect(lambda: drag_ended_called.append(True))

    track = slider._get_track_rect()

    # 1. Press at 10%
    x1 = track.left() + int(track.width() * 0.1)
    ev_press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(float(x1), 15.0),
        QPointF(float(x1), 15.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    slider.mousePressEvent(ev_press)
    assert slider.is_dragging is True
    assert len(drag_started_called) == 1

    # 2. Drag to 40%
    x2 = track.left() + int(track.width() * 0.4)
    ev_move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(float(x2), 15.0),
        QPointF(float(x2), 15.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    slider.mouseMoveEvent(ev_move)
    assert slider._throttle_timer.isActive()

    # Trigger throttle timer directly
    slider._on_throttle_timeout()
    assert abs(seek_values[-1] - 24000) < 500

    # 3. Release at 70%
    x3 = track.left() + int(track.width() * 0.7)
    slider.setValue(slider._pos_to_val(x3))
    ev_release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(float(x3), 15.0),
        QPointF(float(x3), 15.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )
    slider.mouseReleaseEvent(ev_release)

    assert slider.is_dragging is False
    assert len(drag_ended_called) == 1
    assert abs(seek_values[-1] - 42000) < 500


def test_timeline_slider_paint(qapp):
    slider = SIVTimelineSlider()
    slider.resize(500, 30)
    slider.setRange(0, 120000)
    slider.setValue(30000)
    slider.set_chapters([
        {"start": 15.0, "end": 25.0, "title": "Pitch Control"},
        {"start": 60.5, "end": 75.0, "title": "Wingover"}
    ])

    # Test rendering directly into a QPixmap to ensure no exceptions in paintEvent
    pixmap = QPixmap(500, 30)
    pixmap.fill(Qt.GlobalColor.black)
    slider.render(pixmap)
    assert not pixmap.isNull()


def test_timeline_slider_keypress(qapp):
    slider = SIVTimelineSlider()
    slider.setRange(0, 10000)
    slider.setValue(2000)

    seeks = []
    slider.seek_requested.connect(seeks.append)

    key_ev = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Right,
        Qt.KeyboardModifier.NoModifier
    )
    slider.keyPressEvent(key_ev)
    assert len(seeks) == 1


def test_timeline_slider_keyframes(qapp):
    slider = SIVTimelineSlider()
    slider.resize(500, 30)
    slider.setRange(0, 60000)
    slider.set_keyframes({
        "pilot": [{"t": 12.5, "box": [100, 200, 50, 70]}],
        "wing": [{"t": 24.0, "box": [80, 50, 120, 80]}]
    })

    # Verifica snap al keyframe (12.5s -> 12500 ms)
    track = slider._get_track_rect()
    kf_x = slider._val_to_x(12500, track)
    click_x = kf_x + 3  # entro tolleranza di 8px

    seek_values = []
    slider.seek_requested.connect(seek_values.append)

    ev_press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(float(click_x), 15.0),
        QPointF(float(click_x), 15.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    slider.mousePressEvent(ev_press)
    assert slider.value() == 12500

    # Rendering con keyframe diamonds
    pixmap = QPixmap(500, 30)
    pixmap.fill(Qt.GlobalColor.black)
    slider.render(pixmap)
    assert not pixmap.isNull()

    # Clic col tasto destro sul diamante del pilota (12.5s) per eliminarlo
    deleted_events = []
    slider.keyframe_delete_requested.connect(lambda s, t: deleted_events.append((s, t)))

    ev_right_click = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(float(click_x), 15.0),
        QPointF(float(click_x), 15.0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier
    )
    slider.mousePressEvent(ev_right_click)

    assert len(deleted_events) == 1
    assert deleted_events[0][0] == "pilot"
    assert abs(deleted_events[0][1] - 12.5) < 0.05


