import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtCore import Qt

from ui.components.tracking_pip_widget import TrackingPipWidget
from ui.components.tracking_panel import TrackingPanelWidget
from core.sidecar_manager import SidecarData


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_tracking_pip_widget_init_and_zoom(qapp):
    pip = TrackingPipWidget(title="TEST WING", accent_color="#f59e0b")
    assert pip.title == "TEST WING"
    assert pip.accent_color == "#f59e0b"
    assert pip.zoom_factor == 1.0

    # Test zoom-in
    pip._zoom_in()
    assert pip.zoom_factor > 1.0
    assert "x" in pip.btn_zoom_reset.text()

    # Test zoom-out
    pip._zoom_out()
    pip._zoom_out()
    assert pip.zoom_factor == 1.0  # Min clamped to 1.0

    # Test status text
    pip.set_status_text("Testing Status")
    assert "Testing Status" in pip.lbl_viewport.text()


def test_tracking_pip_widget_crop_update(qapp):
    pip = TrackingPipWidget(title="TEST PILOT", accent_color="#38bdf8")
    pip.resize(300, 200)

    # Null crop
    pip.update_crop(None)
    assert "Soggetto non inquadrato" in pip.lbl_viewport.text()

    # Valid image crop
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 0, 0))
    pip.update_crop(img)
    assert pip.lbl_viewport.pixmap() is not None
    assert not pip.lbl_viewport.pixmap().isNull()


def test_tracking_panel_widget_lifecycle(qapp, tmp_path):
    panel = TrackingPanelWidget()
    assert panel.pip_wing is not None
    assert panel.pip_pilot is not None

    # Sidecar without tracking
    mock_video = tmp_path / "flight_test.mp4"
    mock_video.touch()
    sc = SidecarData(str(mock_video))
    panel.set_sidecar(sc)
    assert "In calcolo" in panel.lbl_status.text()

    # Sidecar with tracking
    sc.tracking = {
        "version": "1.0",
        "sample_interval": 0.35,
        "duration": 5.0,
        "video_width": 640,
        "video_height": 480,
        "trajectory": [
            {"t": 0.0, "pilot": [100, 150, 50, 80], "wing": [80, 40, 120, 80]}
        ]
    }
    panel.set_sidecar(sc)
    assert "Sincronizzato" in panel.lbl_status.text()
