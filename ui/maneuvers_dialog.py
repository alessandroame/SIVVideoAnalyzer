import os
from typing import List, Dict, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QListWidget, QListWidgetItem, QInputDialog,
    QMessageBox, QLineEdit, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt
from core.maneuver_detector import ManeuverDetector, DEFAULT_REPEAT_PHRASES

class ManeuversConfigDialog(QDialog):
    """
    Dialog per la gestione avanzata delle manovre SIV e delle frasi di retry:
    - Tab 1: Attivazione/disattivazione mirata manovre per sessione e modifica keyword.
    - Tab 2: Editor frasi di ripetizione/retry ('fanne un'altra', 'riproviamo', ecc.).
    """
    def __init__(self, detector: ManeuverDetector, parent=None):
        super().__init__(parent)
        self.detector = detector
        self.setWindowTitle("⚙️ Configurazione Manovre & Frasi di Retry SIV")
        self.resize(780, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b1120;
                color: #f8fafc;
            }
            QTabWidget::pane {
                border: 1px solid #1e293b;
                background-color: #0f172a;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #1e293b;
                color: #94a3b8;
                padding: 8px 18px;
                font-weight: 600;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #0f172a;
                color: #38bdf8;
                border: 1px solid #1e293b;
                border-bottom: none;
            }
            QTableWidget, QListWidget {
                background-color: #131d35;
                color: #f8fafc;
                border: 1px solid #1e293b;
                border-radius: 6px;
                gridline-color: #1e293b;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #38bdf8;
                font-weight: 700;
                padding: 6px;
                border: none;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #38bdf8;
            }
            QPushButton#btnPrimary {
                background-color: #059669;
                color: white;
                border: none;
            }
            QPushButton#btnPrimary:hover {
                background-color: #10b981;
            }
            QLabel {
                color: #cbd5e1;
            }
        """)

        self.maneuvers_copy = [dict(m) for m in self.detector.all_maneuvers]
        self.enabled_ids = set(self.detector.enabled_maneuver_ids or [m["id"] for m in self.maneuvers_copy])
        self.repeat_phrases = list(self.detector.repeat_phrases)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Tab Widget
        tabs = QTabWidget()

        # TAB 1: MANOVRE SIV
        tab_man = QWidget()
        l_man = QVBoxLayout(tab_man)
        l_man.setSpacing(10)

        lbl_desc = QLabel(
            "💡 <b>Suggerimento didattico:</b> Disattiva le manovre non previste per la giornata/sessione "
            "per azzerare i falsi positivi ed accelerare l'analisi."
        )
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 12px; margin-bottom: 4px;")
        l_man.addWidget(lbl_desc)

        # Tabella Manovre
        self.table_man = QTableWidget(0, 4)
        self.table_man.setHorizontalHeaderLabels(["Attiva", "Categoria", "Nome Manovra", "Parole Chiave Radio (separate da virgola)"])
        self.table_man.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_man.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_man.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_man.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_man.verticalHeader().setVisible(False)
        self.table_man.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        l_man.addWidget(self.table_man)

        # Bottoni rapidi per manovre
        btn_row_man = QHBoxLayout()
        btn_sel_all = QPushButton("☑ Seleziona Tutte")
        btn_sel_all.clicked.connect(lambda: self._set_all_maneuvers_checked(True))
        btn_row_man.addWidget(btn_sel_all)

        btn_desel_all = QPushButton("☐ Deseleziona Tutte")
        btn_desel_all.clicked.connect(lambda: self._set_all_maneuvers_checked(False))
        btn_row_man.addWidget(btn_desel_all)

        btn_add_man = QPushButton("➕ Aggiungi Nuova Manovra")
        btn_add_man.clicked.connect(self._add_custom_maneuver)
        btn_row_man.addWidget(btn_add_man)

        btn_del_man = QPushButton("🗑 Rimuovi Manovra")
        btn_del_man.clicked.connect(self._remove_custom_maneuver)
        btn_row_man.addWidget(btn_del_man)

        btn_row_man.addStretch()
        l_man.addLayout(btn_row_man)

        tabs.addTab(tab_man, "🎯 Manovre SIV & Parole Chiave")

        # TAB 2: FRASI DI RIPETIZIONE (RETRY)
        tab_retry = QWidget()
        l_retry = QVBoxLayout(tab_retry)
        l_retry.setSpacing(10)

        lbl_retry_desc = QLabel(
            "🔁 <b>Riconoscimento automatico delle ripetizioni:</b><br>"
            "Quando l'istruttore pronuncia una di queste frasi alla radio (es. <i>'fanne un'altra'</i>, <i>'riproviamo'</i>), "
            "il sistema crea automaticamente un <b>nuovo capitolo</b> ereditando la manovra precedente."
        )
        lbl_retry_desc.setStyleSheet("color: #94a3b8; font-size: 12px; margin-bottom: 4px;")
        l_retry.addWidget(lbl_retry_desc)

        self.list_retry = QListWidget()
        self.list_retry.setStyleSheet("font-size: 13px; padding: 4px;")
        l_retry.addWidget(self.list_retry)

        btn_row_retry = QHBoxLayout()
        btn_add_retry = QPushButton("➕ Aggiungi Frase di Ripetizione")
        btn_add_retry.clicked.connect(self._add_retry_phrase)
        btn_row_retry.addWidget(btn_add_retry)

        btn_del_retry = QPushButton("🗑 Rimuovi Selezionata")
        btn_del_retry.clicked.connect(self._remove_retry_phrase)
        btn_row_retry.addWidget(btn_del_retry)

        btn_row_retry.addStretch()

        btn_reset_retry = QPushButton("↺ Ripristina Frasi Predefinite")
        btn_reset_retry.clicked.connect(self._reset_default_retry_phrases)
        btn_row_retry.addWidget(btn_reset_retry)

        l_retry.addLayout(btn_row_retry)

        tabs.addTab(tab_retry, "🔁 Frasi di Ripetizione (Retry)")

        layout.addWidget(tabs, stretch=1)

        # Bottoni in fondo alla finestra
        bottom_bar = QHBoxLayout()
        btn_reset_all = QPushButton("↺ Ripristina Tutto ai Valori di Fabbrica")
        btn_reset_all.clicked.connect(self._reset_everything_to_factory)
        bottom_bar.addWidget(btn_reset_all)

        bottom_bar.addStretch()

        btn_cancel = QPushButton("Annulla")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Salva e Applica")
        btn_save.setObjectName("btnPrimary")
        btn_save.clicked.connect(self._save_and_apply)
        bottom_bar.addWidget(btn_save)

        layout.addLayout(bottom_bar)

        self._populate_maneuvers_table()
        self._populate_retry_list()

    def _populate_maneuvers_table(self):
        self.table_man.setRowCount(len(self.maneuvers_copy))
        for r, m in enumerate(self.maneuvers_copy):
            # Checkbox Attiva
            chk = QCheckBox()
            is_checked = m["id"] in self.enabled_ids
            chk.setChecked(is_checked)
            chk.setStyleSheet("margin-left: 10px;")
            self.table_man.setCellWidget(r, 0, chk)

            # Categoria
            cat_item = QTableWidgetItem(m.get("category", "SIV"))
            cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_man.setItem(r, 1, cat_item)

            # Nome
            name_item = QTableWidgetItem(m.get("name", ""))
            name_item.setData(Qt.ItemDataRole.UserRole, m.get("id", ""))
            self.table_man.setItem(r, 2, name_item)

            # Parole chiave
            kws = ", ".join(m.get("keywords", []))
            kw_item = QTableWidgetItem(kws)
            self.table_man.setItem(r, 3, kw_item)

    def _populate_retry_list(self):
        self.list_retry.clear()
        for rp in self.repeat_phrases:
            item = QListWidgetItem(rp)
            self.list_retry.addItem(item)

    def _set_all_maneuvers_checked(self, checked: bool):
        for r in range(self.table_man.rowCount()):
            w = self.table_man.cellWidget(r, 0)
            if isinstance(w, QCheckBox):
                w.setChecked(checked)

    def _add_custom_maneuver(self):
        name, ok = QInputDialog.getText(self, "Nuova Manovra", "Nome della manovra:")
        if not ok or not name.strip():
            return
        name = name.strip()
        cat, ok2 = QInputDialog.getText(self, "Categoria", "Categoria (es. Asimmetriche, Stalli, Dinamica):", text="Personalizzate")
        if not ok2 or not cat.strip():
            cat = "Personalizzate"

        kws, ok3 = QInputDialog.getText(self, "Parole Chiave", "Parole chiave pronunciate alla radio (separate da virgola):", text=name.lower())
        kw_list = [k.strip().lower() for k in kws.split(",") if k.strip()] if ok3 and kws else [name.lower()]

        m_id = name.lower().replace(" ", "_").replace("/", "_")
        new_m = {
            "id": m_id,
            "name": name,
            "category": cat.strip(),
            "keywords": kw_list
        }
        self.maneuvers_copy.append(new_m)
        self.enabled_ids.add(m_id)
        self._populate_maneuvers_table()

    def _remove_custom_maneuver(self):
        curr_row = self.table_man.currentRow()
        if curr_row < 0 or curr_row >= len(self.maneuvers_copy):
            QMessageBox.information(self, "Attenzione", "Seleziona una riga da rimuovere.")
            return

        m = self.maneuvers_copy[curr_row]
        reply = QMessageBox.question(
            self,
            "Conferma Rimozione",
            f"Vuoi davvero eliminare la manovra '{m.get('name')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            m_id = m.get("id")
            self.maneuvers_copy.pop(curr_row)
            self.enabled_ids.discard(m_id)
            self._populate_maneuvers_table()

    def _add_retry_phrase(self):
        phrase, ok = QInputDialog.getText(
            self,
            "Nuova Frase di Ripetizione",
            "Inserisci l'espressione radio dell'istruttore per ripetere la manovra:\n(es. 'ancora una volta', 'falla di nuovo', 'stessa cosa')"
        )
        if ok and phrase.strip():
            p_clean = phrase.strip().lower()
            if p_clean not in self.repeat_phrases:
                self.repeat_phrases.append(p_clean)
                self._populate_retry_list()

    def _remove_retry_phrase(self):
        curr_row = self.list_retry.currentRow()
        if curr_row < 0 or curr_row >= len(self.repeat_phrases):
            return
        self.repeat_phrases.pop(curr_row)
        self._populate_retry_list()

    def _reset_default_retry_phrases(self):
        self.repeat_phrases = list(DEFAULT_REPEAT_PHRASES)
        self._populate_retry_list()

    def _reset_everything_to_factory(self):
        reply = QMessageBox.question(
            self,
            "Ripristino Valori di Fabbrica",
            "Vuoi ripristinare tutte le manovre, le parole chiave e le frasi di retry ai valori predefiniti?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.detector.reset_to_defaults()
            self.maneuvers_copy = [dict(m) for m in self.detector.all_maneuvers]
            self.enabled_ids = set(self.detector.enabled_maneuver_ids or [m["id"] for m in self.maneuvers_copy])
            self.repeat_phrases = list(self.detector.repeat_phrases)
            self._populate_maneuvers_table()
            self._populate_retry_list()
            QMessageBox.information(self, "Ripristino", "Configurazione ripristinata ai valori di fabbrica.")

    def _save_and_apply(self):
        # Raccogli dati dalla tabella
        new_enabled = set()
        updated_maneuvers = []

        for r in range(self.table_man.rowCount()):
            # Checkbox
            w = self.table_man.cellWidget(r, 0)
            is_checked = w.isChecked() if isinstance(w, QCheckBox) else True

            cat_item = self.table_man.item(r, 1)
            cat = cat_item.text().strip() if cat_item else "SIV"

            name_item = self.table_man.item(r, 2)
            name = name_item.text().strip() if name_item else ""
            m_id = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
            if not m_id:
                m_id = name.lower().replace(" ", "_").replace("/", "_")

            kw_item = self.table_man.item(r, 3)
            kws = [k.strip().lower() for k in kw_item.text().split(",") if k.strip()] if kw_item else []

            if is_checked:
                new_enabled.add(m_id)

            updated_maneuvers.append({
                "id": m_id,
                "name": name,
                "category": cat,
                "keywords": kws
            })

        self.detector.save_configuration(
            maneuvers=updated_maneuvers,
            enabled_ids=list(new_enabled),
            repeat_phrases=self.repeat_phrases
        )
        self.accept()
