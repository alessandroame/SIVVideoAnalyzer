import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QImage
from ui.components.siv_video_widget import SIVVideoWidget

@pytest.fixture(scope="module")
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_widget_hit_test_and_cursor(app):
    widget = SIVVideoWidget()
    widget.resize(800, 600)

    # Frame sintetico 1920x1080
    frame = QImage(1920, 1080, QImage.Format.Format_RGB32)
    frame.fill(0)
    widget.display_image(frame)

    # Box pilota a centro video
    widget.set_bounding_boxes(
        pilot_box=(800, 400, 200, 300),
        wing_box=(600, 100, 600, 200),
        force_repaint=False
    )

    # Verifica mapping su schermo
    rp = widget._map_video_box_to_screen(widget._pilot_box)
    assert rp is not None
    assert rp.isValid()

    # Hit test al centro del pilota
    center_p = rp.center()
    subj, handle = widget._hit_test_boxes(center_p)
    assert subj == "pilot"
    assert handle == "move"

    # Hit test sull'angolo in basso a destra (br)
    br_pos = QPoint(rp.right(), rp.bottom())
    subj, handle = widget._hit_test_boxes(br_pos)
    assert subj == "pilot"
    assert handle == "br"

    # Hit test fuori dai box
    outside = QPoint(10, 10)
    subj, handle = widget._hit_test_boxes(outside)
    assert subj is None
    assert handle is None


def test_widget_box_drag_and_signals(app):
    widget = SIVVideoWidget()
    widget.resize(800, 600)

    frame = QImage(1920, 1080, QImage.Format.Format_RGB32)
    frame.fill(0)
    widget.display_image(frame)

    widget.set_bounding_boxes(
        pilot_box=(800, 400, 200, 300),
        wing_box=(600, 100, 600, 200),
        force_repaint=False
    )

    rp = widget._map_video_box_to_screen(widget._pilot_box)

    modified_signals = []
    committed_signals = []
    drag_started_called = []

    widget.box_interactively_modified.connect(lambda s, b: modified_signals.append((s, b)))
    widget.keyframe_committed.connect(lambda s, b: committed_signals.append((s, b)))
    widget.box_drag_started.connect(lambda: drag_started_called.append(True))

    # Simula drag iniziando dal centro del pilota
    start_pos = rp.center()
    widget._drag_target = "pilot"
    widget._drag_handle = "move"
    widget._drag_start_pos = start_pos
    widget._drag_orig_box = list(widget._pilot_box)

    # Calcola spostamento di +20 px su schermo a destra
    rect, sx, sy = widget._get_video_layout()
    move_pos = QPoint(start_pos.x() + 20, start_pos.y())

    # Trigger move manuale simulato
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent
    ev_move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(move_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    widget.mouseMoveEvent(ev_move)

    assert len(modified_signals) == 1
    assert modified_signals[0][0] == "pilot"
    # La coordinata X video deve essere aumentata
    new_x = modified_signals[0][1][0]
    assert new_x > 800

    # Simula mouse release
    ev_release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(move_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier
    )
    widget.mouseReleaseEvent(ev_release)

    assert len(committed_signals) == 1
    assert committed_signals[0][0] == "pilot"
    assert committed_signals[0][1][0] == new_x
    assert widget._drag_target is None
