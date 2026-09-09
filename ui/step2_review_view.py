import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QComboBox, QFrame, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from core.sidecar_manager import SidecarData

class Step2ReviewView(QWidget):
    confirmed_signal = pyqtSignal()
    open_flight_signal = pyqtSignal(str, int) # (pilot_name, flight_number)
    back_signal = pyqtSignal()

    def __init__(self, parent=None, hide_header=False):
        super().__init__(parent)
        self.matches = []
        self.pilots_list = []
        self.hide_header = hide_header
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Header informativo minimale
        self.info_box = QFrame()
        self.info_box.setStyleSheet("""
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
        l_info = QVBoxLayout(self.info_box)
        lbl_title = QLabel("<h2 style='margin:0; color:#38bdf8;'>Revisione Voli (Tra i Voli)</h2>")
        lbl_desc = QLabel("Verifica l'associazione Pilota e Volo per ogni clip. Correggi solo se necessario, poi clicca sul pulsante verde.")
        lbl_desc.setStyleSheet("color: #cbd5e1; font-size: 14px; margin-top: 4px;")
        l_info.addWidget(lbl_title)
        l_info.addWidget(lbl_desc)
        layout.addWidget(self.info_box)
        if self.hide_header:
            self.info_box.setVisible(False)

        # Tabella Video Assegnati essenziale con Azione Rapida
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "File Video", 
            "Pilota", 
            "Volo N°",
            "Chiamata Radio Riconosciuta",
            "Debriefing"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
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

    def reset_data(self, pilots_list=None):
        """Pulisce la tabella all'avvio di una nuova analisi per accogliere le clip in streaming."""
        self.matches = []
        self.pilots_list = list(pilots_list or [])
        if "Da Assegnare" not in self.pilots_list:
            self.pilots_list.append("Da Assegnare")
        self.table.setRowCount(0)

    def add_clip_match(self, match):
        """Aggiunge in tempo reale una clip appena analizzata alla tabella di revisione."""
        self.matches.append(match)
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Colonna 0: File sorgente
        file_item = QTableWidgetItem(match.filename)
        file_item.setFlags(file_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 0, file_item)

        # Colonna 1: ComboBox Pilota
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

        # Colonna 4: Pulsante rapido Guarda Ora
        btn_watch = QPushButton("▶ Guarda Ora")
        btn_watch.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; 
                color: white; 
                font-weight: bold; 
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        # Collega il click per salvare la selezione e aprire il debriefing di quel pilota e volo
        btn_watch.clicked.connect(lambda _, r=row: self.on_watch_clicked(r))
        self.table.setCellWidget(row, 4, btn_watch)

        # Scrolla automaticamente sull'ultima riga aggiunta
        self.table.scrollToBottom()

    def on_watch_clicked(self, row: int):
        # Aggiorna match correnti e salva istantaneamente nel sidecar JSON
        combo = self.table.cellWidget(row, 1)
        spin = self.table.cellWidget(row, 2)
        if combo and row < len(self.matches):
            pilot = combo.currentText().strip() or "Da Assegnare"
            self.matches[row].detected_pilot = pilot
        else:
            pilot = self.matches[row].detected_pilot

        if spin and row < len(self.matches):
            f_num = spin.value()
            self.matches[row].flight_number = f_num
        else:
            f_num = self.matches[row].flight_number

        # Persistenza non distruttiva atomica nel sidecar
        try:
            v_path = getattr(self.matches[row], 'video_path', '')
            if v_path and os.path.exists(v_path):
                sc = SidecarData(v_path)
                sc.pilot_name = pilot
                sc.flight_number = f_num
                sc.confidence = getattr(self.matches[row], 'confidence', 1.0)
                sc.manual_override = True
                sc.save()
        except Exception as e:
            print(f"[Step2] Errore salvataggio sidecar: {e}")

        self.open_flight_signal.emit(pilot, f_num)

    def set_data(self, matches, pilots_list=None):
        self.reset_data(pilots_list)
        for m in matches:
            self.add_clip_match(m)

    def on_confirm(self):
        for row, match in enumerate(self.matches):
            combo = self.table.cellWidget(row, 1)
            spin = self.table.cellWidget(row, 2)
            if combo:
                match.detected_pilot = combo.currentText().strip() or "Da Assegnare"
            if spin:
                match.flight_number = spin.value()

            # Salva in sidecar
            try:
                v_path = getattr(match, 'video_path', '')
                if v_path and os.path.exists(v_path):
                    sc = SidecarData(v_path)
                    sc.pilot_name = match.detected_pilot
                    sc.flight_number = match.flight_number
                    sc.confidence = getattr(match, 'confidence', 1.0)
                    sc.manual_override = True
                    sc.save()
            except Exception as e:
                print(f"[Step2] Errore salvataggio sidecar: {e}")

        self.confirmed_signal.emit()
