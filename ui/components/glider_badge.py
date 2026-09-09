from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor

class GliderBadgeWidget(QWidget):
    """
    Widget compatto per visualizzare la vela e i colori dominanti rilevati
    (es: [🔴][⚫] Advance Iota DLS - Rosso/Nero).
    Cliccabile per aprire la diagnostica dell'analisi dei colori.
    """
    clicked = pyqtSignal()

    def __init__(self, glider_text: str = "", wing_colors: list = None, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("🎨 Clicca sui colori della vela per aprire la Diagnostica Colori")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(6, 2, 6, 2)
        self.layout.setSpacing(6)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.color_container = QWidget()
        self.c_layout = QHBoxLayout(self.color_container)
        self.c_layout.setContentsMargins(0, 0, 0, 0)
        self.c_layout.setSpacing(3)
        self.layout.addWidget(self.color_container)

        self.lbl_text = QLabel(glider_text)
        self.lbl_text.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600;")
        self.layout.addWidget(self.lbl_text)

        self.set_data(glider_text, wing_colors)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def set_data(self, glider_text: str, wing_colors: list = None):
        self.lbl_text.setText(glider_text or "—")

        # Pulisce i pallini precedenti
        while self.c_layout.count():
            item = self.c_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if wing_colors:
            for c in wing_colors:
                hex_val = c.get("hex", "#94a3b8")
                name_val = c.get("name", "")
                dot = QFrame()
                dot.setFixedSize(12, 12)
                dot.setStyleSheet(f"""
                    QFrame {{
                        background-color: {hex_val};
                        border: 1px solid #475569;
                        border-radius: 6px;
                    }}
                """)
                dot.setToolTip(f"Colore vela rilevato: {name_val} (Clicca per Diagnostica)")
                self.c_layout.addWidget(dot)
            self.color_container.setVisible(True)
        else:
            self.color_container.setVisible(False)

