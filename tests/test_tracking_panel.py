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


def test_tracking_pip_widget_pan_and_reset(qapp):
    pip = TrackingPipWidget(title="TEST PAN", accent_color="#f59e0b")
    pip.resize(300, 200)

    img = QImage(640, 360, QImage.Format.Format_RGB32)
    img.fill(QColor(100, 150, 200))
    pip.update_crop(img)

    assert pip.zoom_factor == 1.0
    assert pip.pan_norm_x == 0.0
    assert pip.pan_norm_y == 0.0

    # Zoom in
    pip._zoom_in()
    pip._zoom_in()
    assert pip.zoom_factor >= 1.5

    # Pan
    pip.pan_norm_x = 0.5
    pip.pan_norm_y = -0.5
    pip.update_crop(img)
    assert pip.pan_norm_x == 0.5
    assert pip.pan_norm_y == -0.5

    # Reset
    pip._reset_zoom()
    assert pip.zoom_factor == 1.0
    assert pip.pan_norm_x == 0.0
    assert pip.pan_norm_y == 0.0


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


def test_tracking_panel_wide_crop_rect(qapp):
    # Test che anche con una bounding box stretta e verticale (1:2.5)
    # il rettangolo calcolato sia sempre largo panoramico (>= 1.5 aspect ratio)
    narrow_box = (800, 300, 100, 250)
    img_w, img_h = 1920, 1080
    crop_rect = TrackingPanelWidget._compute_wide_crop_rect(
        box=narrow_box,
        img_w=img_w,
        img_h=img_h,
        target_ar=16.0 / 9.0,
        pad_factor=1.45
    )

    assert crop_rect is not None
    assert not crop_rect.isEmpty()
    # Verifica che la larghezza sia maggiore dell'altezza (vista larga)
    assert crop_rect.width() > crop_rect.height()
    aspect_ratio = crop_rect.width() / crop_rect.height()
    assert aspect_ratio >= 1.5
    # Verifica che il centro del soggetto originale sia incluso nel crop
    center_x = narrow_box[0] + narrow_box[2] // 2
    center_y = narrow_box[1] + narrow_box[3] // 2
    assert crop_rect.contains(center_x, center_y)


def test_tracking_panel_throttling(qapp, tmp_path):
    panel = TrackingPanelWidget()
    panel.show()

    mock_video = tmp_path / "flight_test2.mp4"
    mock_video.touch()
    sc = SidecarData(str(mock_video))
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

    img = QImage(640, 480, QImage.Format.Format_RGBA8888)
    img.fill(QColor(10, 20, 30))

    # Prima chiamata (forzata o non): aggiorna
    panel.handle_qimage_frame(img, 0.0, force=True)
    assert panel.pip_wing._current_crop_image is not None
    t0 = panel._last_update_time

    # Seconda chiamata immediata (non forzata): throttled (nessun ricalcolo)
    panel.handle_qimage_frame(img, 0.0, force=False)
    assert panel._last_update_time == t0

    # Terza chiamata forzata: ignora il throttle
    panel.handle_qimage_frame(img, 0.0, force=True)
    assert panel._last_update_time >= t0


def test_tracking_panel_deinterlace_crop(qapp):
    w, h = 64, 64
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(QColor(0, 0, 0, 255))
    for y in range(0, h, 2):
        for x in range(w):
            img.setPixelColor(x, y, QColor(180, 180, 180, 255))

    deint = TrackingPanelWidget._deinterlace_crop(img)
    assert deint.pixelColor(10, 1).red() == 180

