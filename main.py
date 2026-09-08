import sys
import os

# Sopprime il warning informativo sui symlink di Windows per HuggingFace
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
