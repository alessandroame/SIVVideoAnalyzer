import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QColor, QKeyEvent
from PyQt6.QtCore import Qt, QEvent, QRect
from PyQt6.QtMultimedia import QVideoFrame

from ui.components.siv_video_widget import SIVVideoWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_siv_video_widget_init(qapp):
    widget = SIVVideoWidget()
    assert widget.videoSink() is not None
    assert widget.show_bounding_boxes is True
    assert widget.isFullScreen() is False


def test_siv_video_widget_toggle_boxes(qapp):
    widget = SIVVideoWidget()
    assert widget.show_bounding_boxes is True

    new_state = widget.toggle_bounding_boxes()
    assert new_state is False
    assert widget.show_bounding_boxes is False

    new_state = widget.toggle_bounding_boxes()
    assert new_state is True
    assert widget.show_bounding_boxes is True

    widget.set_show_bounding_boxes(False)
    assert widget.show_bounding_boxes is False


def test_siv_video_widget_boxes_setting(qapp):
    widget = SIVVideoWidget()
    p_box = (100, 200, 50, 80)
    w_box = (80, 50, 200, 100)

    widget.set_bounding_boxes(p_box, w_box)
    assert widget._pilot_box == p_box
    assert widget._wing_box == w_box

    widget.set_bounding_boxes(None, None)
    assert widget._pilot_box is None
    assert widget._wing_box is None


def test_siv_video_widget_deinterlace_filter(qapp):
    w, h = 64, 64
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(QColor(0, 0, 0, 255))

    for y in range(0, h, 2):
        for x in range(w):
            img.setPixelColor(x, y, QColor(200, 200, 200, 255))

    assert img.pixelColor(10, 1).red() == 0

    deint = SIVVideoWidget._deinterlace_image(img)
    assert deint.pixelColor(10, 1).red() == 200


def test_siv_video_widget_paint_event_and_rendering(qapp):
    widget = SIVVideoWidget()
    widget.resize(640, 360)

    img = QImage(1920, 1080, QImage.Format.Format_RGBA8888)
    img.fill(QColor(30, 60, 120))
    widget._current_frame = img

    widget.set_bounding_boxes(pilot_box=(900, 500, 100, 150), wing_box=(700, 200, 400, 200))

    pix = widget.grab()
    assert pix is not None
    assert not pix.isNull()
    assert pix.width() == 640
    assert pix.height() == 360


def test_siv_video_widget_keypress_shortcuts(qapp):
    widget = SIVVideoWidget()
    signals_received = []

    widget.toggle_boxes_requested.connect(lambda: signals_received.append('boxes'))
    widget.toggle_tracking_requested.connect(lambda: signals_received.append('tracking'))
    widget.toggle_play_requested.connect(lambda: signals_received.append('play'))

    ev_b = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(ev_b)
    assert 'boxes' in signals_received
    assert widget.show_bounding_boxes is False

    ev_t = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_T, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(ev_t)
    assert 'tracking' in signals_received

    ev_sp = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(ev_sp)
    assert 'play' in signals_received


def test_siv_video_widget_frame_decoded_signal(qapp):
    widget = SIVVideoWidget()
    received_frames = []
    widget.frame_decoded.connect(lambda img: received_frames.append(img))

    # Test simulando l'arrivo di un frame valido da QVideoFrame
    raw_img = QImage(160, 90, QImage.Format.Format_RGBA8888)
    raw_img.fill(QColor(100, 150, 200))
    video_frame = QVideoFrame(raw_img)
    widget._on_video_frame(video_frame)

    assert len(received_frames) == 1
    assert not received_frames[0].isNull()
    assert received_frames[0].width() == 160
    assert received_frames[0].height() == 90


def test_siv_video_widget_set_bounding_boxes_force_repaint(qapp):
    widget = SIVVideoWidget()
    widget.set_show_bounding_boxes(True)

    # force_repaint=False non genera repaint immediato, aggiorna solo i dati
    widget.set_bounding_boxes((10, 20, 30, 40), (50, 60, 70, 80), force_repaint=False)
    assert widget._pilot_box == (10, 20, 30, 40)
    assert widget._wing_box == (50, 60, 70, 80)


def test_siv_video_widget_arrow_keys(qapp):
    widget = SIVVideoWidget()
    arrow_events = []
    seek_events = []

    widget.arrow_nav_requested.connect(lambda d: arrow_events.append(d))
    widget.seek_requested.connect(lambda ms: seek_events.append(ms))

    ev_left = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(ev_left)
    assert arrow_events == [-1]
    assert seek_events == [-5000]

    ev_right = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(ev_right)
    assert arrow_events == [-1, 1]
    assert seek_events == [-5000, 5000]

