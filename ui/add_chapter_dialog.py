from typing import List, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTimeEdit, QCompleter, QLineEdit
)
from PyQt6.QtCore import Qt, QTime

class AddChapterQuickDialog(QDialog):
    """
    Dialog compatto per aggiungere o modificare rapidamente una manovra/capitolo nel Player di debriefing.
    Offre:
    - Campo di selezione rapida basato sull'elenco delle manovre SIV attive con autocompletamento.
    - Possibilità di inserire qualsiasi testo libero/nota.
    - Selezione del timestamp di inizio manovra (default al secondo corrente del video).
    - Tasto Invio immediato per confermare senza interruzioni cognitive.
    """
    def __init__(self, current_seconds: float, active_maneuvers: List[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("➕ Aggiungi Manovra / Capitolo")
        self.setFixedWidth(460)
        self.selected_title = ""
        self.selected_time = current_seconds
        self.selected_category = "SIV"

        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f8fafc;
            }
            QLabel {
                font-size: 13px;
                color: #cbd5e1;
                font-weight: 600;
            }
            QComboBox, QLineEdit {
                background-color: #1e293b;
                color: #ffffff;
                border: 1.5px solid #334155;
                border-radius: 6px;
                padding: 7px 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QComboBox:hover, QLineEdit:hover {
                border-color: #38bdf8;
            }
            QComboBox QAbstractItemView {
                background-color: #1e293b;
                color: #ffffff;
                selection-background-color: #0284c7;
                border: 1px solid #334155;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
            }
            QPushButton#btnPrimary {
                background-color: #059669;
                color: #ffffff;
                border: none;
                font-weight: 700;
            }
            QPushButton#btnPrimary:hover {
                background-color: #10b981;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Minutaggio
        t_sec = int(current_seconds)
        time_str = f"{t_sec // 60:02d}:{t_sec % 60:02d}"
        lbl_time = QLabel(f"⏱ <b>Posizione nel Video:</b> {time_str} ({t_sec}s)")
        lbl_time.setStyleSheet("color: #38bdf8; font-size: 13px;")
        layout.addWidget(lbl_time)

        # Selettore Manovra
        layout.addWidget(QLabel("Seleziona Manovra SIV (oppure digita testo libero):"))

        self.combo_maneuvers = QComboBox()
        self.combo_maneuvers.setEditable(True)
        self.combo_maneuvers.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        # Popola con le manovre attive raggruppate o ordinate
        sorted_man = sorted(active_maneuvers, key=lambda m: (m.get("category", ""), m.get("name", "")))
        
        maneuver_names = []
        for m in sorted_man:
            cat = m.get("category", "")
            prefix = f"[{cat}] " if cat else ""
            display = f"{prefix}{m.get('name')}"
            self.combo_maneuvers.addItem(display, m)
            maneuver_names.append(display)
            maneuver_names.append(m.get("name"))

        completer = QCompleter(maneuver_names, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo_maneuvers.setCompleter(completer)

        layout.addWidget(self.combo_maneuvers)

        # Note opzionali
        layout.addWidget(QLabel("Note / Dettaglio (opzionale):"))
        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("Es. '30% destra', 'uscita progressiva', ecc.")
        layout.addWidget(self.txt_notes)

        # Bottoni
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_confirm = QPushButton("✓ Conferma (Invio)")
        btn_confirm.setObjectName("btnPrimary")
        btn_confirm.clicked.connect(self._on_confirm)
        btn_box.addWidget(btn_confirm)

        layout.addLayout(btn_box)

        # Focus immediato sull'input della manovra
        self.combo_maneuvers.setFocus()
        if self.combo_maneuvers.lineEdit():
            self.combo_maneuvers.lineEdit().selectAll()

    def _on_confirm(self):
        text = self.combo_maneuvers.currentText().strip()
        if not text:
            text = "Manovra SIV"

        # Se il testo inizia con [Categoria], rimuoviamo la categoria dal titolo
        cat = "SIV"
        if text.startswith("[") and "] " in text:
            parts = text.split("] ", 1)
            cat = parts[0].strip("[]")
            title = parts[1].strip()
        else:
            title = text
            # Controlla se corrisponde ai dati
            item_data = self.combo_maneuvers.currentData()
            if isinstance(item_data, dict):
                cat = item_data.get("category", "SIV")

        notes = self.txt_notes.text().strip()
        if notes:
            title = f"{title} ({notes})"

        self.selected_title = title
        self.selected_category = cat
        self.accept()
