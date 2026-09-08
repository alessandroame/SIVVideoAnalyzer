import sys
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QFileDialog, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt

class SorterApprovalDialog(QDialog):
    def __init__(self, matches, pilots_list=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Revisione e Approvazione Suddivisione Piloti")
        self.resize(750, 480)
        self.matches = matches
        self.pilots_list = pilots_list or []
        if "Da Assegnare" not in self.pilots_list:
            self.pilots_list.append("Da Assegnare")
            
        self.confirmed = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        info_label = QLabel(
            "<b>Verifica l'assegnazione dei video ai piloti rilevati dall'audio radio.</b><br>"
            "Puoi modificare manualmente il pilota associato a ciascun video prima di procedere allo smistamento."
        )
        layout.addWidget(info_label)

        # Tabella
        self.table = QTableWidget(len(self.matches), 4)
        self.table.setHorizontalHeaderLabels(["File Video", "Pilota Rilevato / Assegnato", "Confidenza", "Frasi Radio Identificate"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        for row, match in enumerate(self.matches):
            # Colonna 0: File
            file_item = QTableWidgetItem(match.filename)
            file_item.setFlags(file_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, file_item)

            # Colonna 1: ComboBox Piloti
            combo = QComboBox()
            # Inserisci i piloti noti
            all_pilots = list(dict.fromkeys(self.pilots_list + [match.detected_pilot]))
            combo.addItems(all_pilots)
            idx = combo.findText(match.detected_pilot)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.setEditable(True)  # permette di digitare un nuovo nome pilota
            self.table.setCellWidget(row, 1, combo)

            # Colonna 2: Confidenza
            conf_percent = f"{int(match.confidence * 100)}%"
            conf_item = QTableWidgetItem(conf_percent)
            conf_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            conf_item.setFlags(conf_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, conf_item)

            # Colonna 3: Frasi Rilevate
            phrases_text = " | ".join(match.matched_phrases) if match.matched_phrases else "Nessuna chiamata esplicita"
            phrases_item = QTableWidgetItem(phrases_text)
            phrases_item.setFlags(phrases_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, phrases_item)

        layout.addWidget(self.table)

        # Pulsanti
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Annulla")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch()

        self.btn_confirm = QPushButton("Approva e Smista Video")
        self.btn_confirm.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 16px;")
        self.btn_confirm.clicked.connect(self.on_confirm)
        btn_layout.addWidget(self.btn_confirm)

        layout.addLayout(btn_layout)

    def on_confirm(self):
        # Aggiorna i match con le selezioni effettive dell'utente
        for row, match in enumerate(self.matches):
            combo = self.table.cellWidget(row, 1)
            if combo:
                match.detected_pilot = combo.currentText().strip() or "Da Assegnare"
        self.confirmed = True
        self.accept()
