import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QComboBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal

class Step2ReviewView(QWidget):
    confirmed_signal = pyqtSignal()
    back_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.matches = []
        self.pilots_list = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header informativo (dark theme coerente con contrasto elevato)
        info_box = QFrame()
        info_box.setStyleSheet("""
            QFrame {
                background-color: #1e293b; 
                border-radius: 6px; 
                padding: 10px;
                border: 1px solid #334155;
            }
            QLabel {
                color: #f1f5f9;
            }
        """)
        l_info = QVBoxLayout(info_box)
        lbl_title = QLabel("<h2>Revisione e Assegnazione Video</h2>")
        lbl_title.setStyleSheet("color: #38bdf8; font-weight: bold; margin-bottom: 2px;")
        lbl_desc = QLabel(
            "Verifica l'associazione rilevata dall'ascolto radio per ciascun video del corso.<br>"
            "Puoi correggere il pilota assegnato tramite il menu a tendina o digitare un nuovo nome pilota prima di procedere al montaggio."
        )
        lbl_desc.setStyleSheet("color: #cbd5e1; font-size: 13px;")
        l_info.addWidget(lbl_title)
        l_info.addWidget(lbl_desc)
        layout.addWidget(info_box)

        # Tabella Video Assegnati
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "File Video Sorgente", 
            "Pilota Rilevato / Assegnato", 
            "Confidenza Radio", 
            "Frasi Radio Chiave Riconosciute"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Barra Pulsanti Navigazione
        btn_layout = QHBoxLayout()
        self.btn_back = QPushButton("⬅ Torna a Configurazione")
        self.btn_back.setStyleSheet("padding: 8px 16px; font-size: 13px;")
        self.btn_back.clicked.connect(self.back_signal.emit)
        btn_layout.addWidget(self.btn_back)

        btn_layout.addStretch()

        self.btn_confirm = QPushButton("Conferma e Crea Video Montati per Pilota ➡")
        self.btn_confirm.setStyleSheet(
            "background-color: #2e7d32; color: white; font-weight: bold; font-size: 13px; padding: 10px 22px; border-radius: 4px;"
        )
        self.btn_confirm.clicked.connect(self.on_confirm)
        btn_layout.addWidget(self.btn_confirm)

        layout.addLayout(btn_layout)

    def set_data(self, matches, pilots_list=None):
        self.matches = matches
        self.pilots_list = list(pilots_list or [])
        if "Da Assegnare" not in self.pilots_list:
            self.pilots_list.append("Da Assegnare")

        self.table.setRowCount(len(matches))
        for row, match in enumerate(matches):
            file_item = QTableWidgetItem(match.filename)
            file_item.setFlags(file_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, file_item)

            combo = QComboBox()
            all_pilots = list(dict.fromkeys(self.pilots_list + [match.detected_pilot]))
            combo.addItems(all_pilots)
            idx = combo.findText(match.detected_pilot)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.setEditable(True)
            self.table.setCellWidget(row, 1, combo)

            conf_percent = f"{int(match.confidence * 100)}%"
            conf_item = QTableWidgetItem(conf_percent)
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            conf_item.setFlags(conf_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, conf_item)

            phrases_text = " | ".join(match.matched_phrases) if match.matched_phrases else "Nessuna chiamata radio esplicita"
            phrases_item = QTableWidgetItem(phrases_text)
            phrases_item.setFlags(phrases_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, phrases_item)

    def on_confirm(self):
        for row, match in enumerate(self.matches):
            combo = self.table.cellWidget(row, 1)
            if combo:
                match.detected_pilot = combo.currentText().strip() or "Da Assegnare"
        self.confirmed_signal.emit()
