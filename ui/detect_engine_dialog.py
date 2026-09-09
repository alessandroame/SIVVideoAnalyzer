from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame
)
from PyQt6.QtCore import Qt

class DetectManeuversEngineDialog(QDialog):
    """
    Dialog modale per selezionare l'engine / modello Whisper prima di eseguire
    il rilevamento manovre per il video in riproduzione.
    """
    def __init__(self, current_model: str = "small", parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 Rileva Manovre - Selezione Engine")
        self.setFixedWidth(440)
        self.selected_model = current_model or "small"
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f8fafc;
            }
            QLabel {
                font-size: 13px;
                color: #cbd5e1;
            }
            QComboBox {
                background-color: #1e293b;
                color: #ffffff;
                border: 1.5px solid #334155;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: 600;
            }
            QComboBox:hover {
                border-color: #38bdf8;
            }
            QComboBox QAbstractItemView {
                background-color: #1e293b;
                color: #ffffff;
                selection-background-color: #0284c7;
                border: 1px solid #334155;
                padding: 4px;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 9px 18px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #64748b;
            }
            QPushButton#btnConfirm {
                background-color: #0891b2;
                color: #ffffff;
                border: none;
            }
            QPushButton#btnConfirm:hover {
                background-color: #06b6d4;
            }
            QPushButton#btnConfirm:pressed {
                background-color: #0e7490;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl_title = QLabel("Seleziona il modello Whisper:")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #f8fafc;")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel("Il motore analizzerà l'audio radio per estrarre parole chiave e timestamp delle manovre SIV.")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(lbl_desc)

        self.combo_engine = QComboBox()
        self.combo_engine.addItem("⚡ Whisper Small (Bilanciato & Veloce - Consigliato)", "small")
        self.combo_engine.addItem("🎯 Whisper Medium (Alta Precisione per audio con vento)", "medium")
        self.combo_engine.addItem("🧠 Whisper Large-v3 (Massima Accuratezza)", "large-v3")

        for i in range(self.combo_engine.count()):
            if self.combo_engine.itemData(i) == self.selected_model:
                self.combo_engine.setCurrentIndex(i)
                break
        layout.addWidget(self.combo_engine)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #1e293b;")
        layout.addWidget(line)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton("🚀 Avvia Rilevamento")
        btn_ok.setObjectName("btnConfirm")
        btn_ok.clicked.connect(self._on_confirm)
        btn_box.addWidget(btn_ok)

        layout.addLayout(btn_box)

    def _on_confirm(self):
        self.selected_model = self.combo_engine.currentData()
        self.accept()
