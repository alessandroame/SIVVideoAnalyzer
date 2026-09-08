import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QComboBox, QFrame, QSpinBox
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

        # Header informativo minimale
        info_box = QFrame()
        info_box.setStyleSheet("""
            QFrame {
                background-color: #1e293b; 
                border-radius: 8px; 
                padding: 12px 16px;
                border: 1px solid #334155;
            }
            QLabel {
                color: #f1f5f9;
            }
        """)
        l_info = QVBoxLayout(info_box)
        lbl_title = QLabel("<h2 style='margin:0; color:#38bdf8;'>Revisione Voli (Tra i Voli)</h2>")
        lbl_desc = QLabel("Verifica l'associazione Pilota e Volo per ogni clip. Correggi solo se necessario, poi clicca sul pulsante verde.")
        lbl_desc.setStyleSheet("color: #cbd5e1; font-size: 14px; margin-top: 4px;")
        l_info.addWidget(lbl_title)
        l_info.addWidget(lbl_desc)
        layout.addWidget(info_box)

        # Tabella Video Assegnati essenziale (meno colonne dispersive)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "File Video", 
            "Pilota", 
            "Volo N°",
            "Chiamata Radio Riconosciuta"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("""
            QTableWidget {
                font-size: 14px;
                selection-background-color: #0284c7;
            }
            QHeaderView::section {
                font-size: 13px;
                font-weight: bold;
                padding: 6px;
            }
        """)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Barra Pulsanti Navigazione
        btn_layout = QHBoxLayout()
        self.btn_back = QPushButton("⬅ Indietro")
        self.btn_back.setStyleSheet("padding: 10px 18px; font-size: 14px; font-weight: 500;")
        self.btn_back.clicked.connect(self.back_signal.emit)
        btn_layout.addWidget(self.btn_back)

        btn_layout.addStretch()

        self.btn_confirm = QPushButton("➡ ENTRA NEL DEBRIEFING (Zero Attese)")
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #16a34a; 
                color: white; 
                font-weight: bold; 
                font-size: 15px; 
                padding: 12px 28px; 
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #15803d;
            }
        """)
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
            # Colonna 0: File sorgente
            file_item = QTableWidgetItem(match.filename)
            file_item.setFlags(file_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, file_item)

            # Colonna 1: ComboBox Pilota (più comodo da selezionare)
            combo = QComboBox()
            combo.setStyleSheet("font-size: 14px; padding: 4px;")
            all_pilots = list(dict.fromkeys(self.pilots_list + [match.detected_pilot]))
            combo.addItems(all_pilots)
            idx = combo.findText(match.detected_pilot)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.setEditable(True)
            self.table.setCellWidget(row, 1, combo)

            # Colonna 2: SpinBox Numero di Volo
            spin_volo = QSpinBox()
            spin_volo.setRange(1, 99)
            flight_num = getattr(match, 'flight_number', 1) or 1
            spin_volo.setValue(flight_num)
            spin_volo.setStyleSheet("padding: 4px; font-size: 14px; font-weight: bold;")
            self.table.setCellWidget(row, 2, spin_volo)

            # Colonna 3: Frasi Rilevate (chiamata radio)
            phrases_text = " | ".join(match.matched_phrases) if match.matched_phrases else "—"
            phrases_item = QTableWidgetItem(phrases_text)
            phrases_item.setFlags(phrases_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, phrases_item)

    def on_confirm(self):
        for row, match in enumerate(self.matches):
            combo = self.table.cellWidget(row, 1)
            spin = self.table.cellWidget(row, 2)
            if combo:
                match.detected_pilot = combo.currentText().strip() or "Da Assegnare"
            if spin:
                match.flight_number = spin.value()
        self.confirmed_signal.emit()
