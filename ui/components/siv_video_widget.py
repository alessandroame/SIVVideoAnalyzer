from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtMultimediaWidgets import QVideoWidget


class SIVVideoWidget(QVideoWidget):
    """
    QVideoWidget con gestione integrata della tastiera in modalità a tutto schermo
    e supporto all'overlay dei riquadri di tracciamento.
    """
    escape_pressed = pyqtSignal()
    toggle_fullscreen_requested = pyqtSignal()
    toggle_play_requested = pyqtSignal()
    seek_requested = pyqtSignal(int)
    toggle_tracking_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracking_overlay = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.tracking_overlay:
            self.tracking_overlay.setGeometry(self.rect())

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.setFullScreen(False)
            self.escape_pressed.emit()
            event.accept()
        elif key == Qt.Key.Key_F:
            self.setFullScreen(not self.isFullScreen())
            self.toggle_fullscreen_requested.emit()
            event.accept()
        elif key == Qt.Key.Key_T:
            self.toggle_tracking_requested.emit()
            event.accept()
        elif key == Qt.Key.Key_Space:
            self.toggle_play_requested.emit()
            event.accept()
        elif key == Qt.Key.Key_Left:
            self.seek_requested.emit(-5000)
            event.accept()
        elif key == Qt.Key.Key_Right:
            self.seek_requested.emit(5000)
            event.accept()
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.setFullScreen(not self.isFullScreen())
        self.toggle_fullscreen_requested.emit()
        event.accept()
