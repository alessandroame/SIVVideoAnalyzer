import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QComboBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont

from core.sidecar_manager import SidecarData
from core.audio_extractor import get_formatted_video_datetime
from core.pilot_detector import VideoPilotMatch
from ui.components import ensure_arrow_icons

ARROW_UP_PATH, ARROW_DOWN_PATH = ensure_arrow_icons()

class FlightTableWidget(QWidget):
    """Componente autonomo per la gestione del Registro Voli Live."""
    back_to_config_requested = pyqtSignal()
    open_debriefing_requested = pyqtSignal(str)
    export_all_requested = pyqtSignal()
    reset_analysis_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.known_pilots = []
        self.pilot_gliders = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(0, 0, 0, 0)

        # Barra superiore
        top = QHBoxLayout()
        top.setSpacing(12)

        btn_back = QPushButton("⬅ Torna alla Configurazione")
        btn_back.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
                background-color: #131b2e;
                color: #94a3b8;
                border: 1px solid #23314f;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #1c263d;
                color: #ffffff;
                border-color: #38bdf8;
            }
        """)
        btn_back.clicked.connect(self.back_to_config_requested.emit)
        top.addWidget(btn_back)

        self.lbl_table_header = QLabel("Voli Rilevati")
        self.lbl_table_header.setStyleSheet("font-size: 18px; font-weight: 700; color: #f8fafc;")
        top.addWidget(self.lbl_table_header)

        top.addStretch()

        self.lbl_worker_status = QLabel("")
        self.lbl_worker_status.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 13px;")
        top.addWidget(self.lbl_worker_status)

        self.progress_overall = QProgressBar()
        self.progress_overall.setFixedWidth(180)
        self.progress_overall.setFixedHeight(14)
        self.progress_overall.setStyleSheet("""
            QProgressBar {
                border: 1px solid #23314f;
                border-radius: 7px;
                text-align: center;
                background-color: #0b111e;
                color: white;
                font-size: 10px;
                font-weight: 700;
            }
            QProgressBar::chunk {
                background-color: #06b6d4;
                border-radius: 6px;
            }
        """)
        self.progress_overall.setVisible(False)
        top.addWidget(self.progress_overall)

        btn_export_all = QPushButton("🎬 Esporta Tutti i Voli")
        btn_export_all.setStyleSheet("""
            QPushButton {
                padding: 8px 14px;
                font-weight: 700;
                font-size: 12px;
                background-color: #059669;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #10b981; }
            QPushButton:pressed { background-color: #047857; }
        """)
        btn_export_all.setToolTip("Esporta tutti i voli dei piloti riconosciuti nella cartella di destinazione.")
        btn_export_all.clicked.connect(self.export_all_requested.emit)
        top.addWidget(btn_export_all)

        btn_reset = QPushButton("🔄 Reset & Rianalizza")
        btn_reset.setStyleSheet("""
            QPushButton {
                padding: 8px 14px;
                font-weight: 600;
                font-size: 12px;
                background-color: #881337;
                color: #fecdd3;
                border: 1px solid #9f1239;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #be123c;
                color: white;
                border-color: #e11d48;
            }
        """)
        btn_reset.setToolTip("Cancella i riconoscimenti salvati per questa sessione e riesegue l'analisi da zero.")
        btn_reset.clicked.connect(self.reset_analysis_requested.emit)
        top.addWidget(btn_reset)
        layout.addLayout(top)

        # Tabella Voli (8 Colonne)
        self.table_flights = QTableWidget(0, 8)
        self.table_flights.setHorizontalHeaderLabels([
            "File Video", "Data e Ora", "Volo N°", "Pilota Assegnato", "Vela / Colore", "Esito / Certezza", "Chiamata Radio Riconosciuta", "Debriefing"
        ])
        self.table_flights.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table_flights.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.verticalHeader().setDefaultSectionSize(42)
        self.table_flights.verticalHeader().setVisible(False)
        self.table_flights.setShowGrid(False)

        self.table_flights.cellChanged.connect(self._on_table_cell_edited)
        self.table_flights.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table_flights)

        hint = QLabel("💡 <b>Suggerimento:</b> Doppio clic su una riga per aprire il Debriefing. Puoi selezionare il Pilota dal menù o cambiare il N° di volo con le frecce.")
        hint.setStyleSheet("color: #64748b; font-size: 12px; margin-top: 2px;")
        layout.addWidget(hint)

    def set_session_info(self, title: str, pilots: list, gliders: dict):
        self.lbl_table_header.setText(title)
        self.known_pilots = list(pilots)
        self.pilot_gliders = dict(gliders)
        self.table_flights.setRowCount(0)

    def set_worker_status(self, text: str):
        self.lbl_worker_status.setText(text)

    def update_overall_progress(self, eta_text: str, percent: int):
        self.lbl_worker_status.setText(eta_text)
        self.progress_overall.setVisible(True)
        self.progress_overall.setValue(percent)
        if percent >= 100:
            self.progress_overall.setStyleSheet(self.progress_overall.styleSheet() + "QProgressBar::chunk { background-color: #16a34a; }")

    def hide_progress(self):
        self.progress_overall.setVisible(False)

    def calculate_auto_flight_number(self, pilot_name: str, current_row: int) -> int:
        if not pilot_name or pilot_name in ["In attesa...", "Da Assegnare"]:
            return 1
        count = 0
        for r in range(self.table_flights.rowCount()):
            p_combo = self.table_flights.cellWidget(r, 3)
            row_pilot = p_combo.currentText() if isinstance(p_combo, QComboBox) else ""
            if row_pilot.strip().lower() == pilot_name.strip().lower():
                count += 1
                if r == current_row:
                    return count
        return max(1, count)

    def add_flight_row(self, video_path: str, pilot: str, flight_num: int, glider: str, phrases: str, is_confirmed: bool, confidence: float = 1.0, recorded_at: str = ""):
        row = self.table_flights.rowCount()
        self.table_flights.blockSignals(True)
        self.table_flights.insertRow(row)

        # Colonna 0: File Video
        fname = os.path.basename(video_path)
        item_file = QTableWidgetItem(fname)
        item_file.setFlags(item_file.flags() ^ Qt.ItemFlag.ItemIsEditable)
        item_file.setData(Qt.ItemDataRole.UserRole, video_path)
        self.table_flights.setItem(row, 0, item_file)

        # Colonna 1: Data e Ora
        if not recorded_at:
            recorded_at = get_formatted_video_datetime(video_path)
        item_dt = QTableWidgetItem(recorded_at)
        item_dt.setFlags(item_dt.flags() ^ Qt.ItemFlag.ItemIsEditable)
        item_dt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_dt.setForeground(QBrush(QColor("#94a3b8")))
        item_dt.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.table_flights.setItem(row, 1, item_dt)

        # Colonna 2: Volo N°
        spin_flight = QSpinBox()
        spin_flight.setRange(1, 99)
        spin_flight.setValue(flight_num if flight_num and flight_num > 0 else 1)
        spin_flight.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin_flight.setStyleSheet(f"""
            QSpinBox {{
                background-color: #1a253c;
                color: #f8fafc;
                border: 1px solid #2a3b5c;
                border-radius: 6px;
                padding: 3px 22px 3px 8px;
                font-weight: 700;
                font-size: 13px;
            }}
            QSpinBox:hover {{ border-color: #06b6d4; }}
            QSpinBox:focus {{ border: 1.5px solid #06b6d4; }}
            QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                background-color: #23314f;
                border-top-right-radius: 5px;
                border-bottom: 1px solid #1a253c;
            }}
            QSpinBox::up-button:hover {{ background-color: #0891b2; }}
            QSpinBox::up-arrow {{ image: url("{ARROW_UP_PATH}"); width: 10px; height: 10px; }}
            QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                background-color: #23314f;
                border-bottom-right-radius: 5px;
            }}
            QSpinBox::down-button:hover {{ background-color: #0891b2; }}
            QSpinBox::down-arrow {{ image: url("{ARROW_DOWN_PATH}"); width: 10px; height: 10px; }}
        """)
        spin_flight.valueChanged.connect(lambda val, r=row, p=video_path: self._on_flight_spin_changed(r, p, val))
        self.table_flights.setCellWidget(row, 2, spin_flight)

        # Colonna 3: Pilota Assegnato
        combo_pilot = QComboBox()
        combo_pilot.setEditable(True)
        combo_pilot.addItem("Da Assegnare")
        for p in self.known_pilots:
            if p not in ["Da Assegnare"]:
                combo_pilot.addItem(p)

        if pilot and pilot not in ["In attesa...", "Da Assegnare"]:
            idx = combo_pilot.findText(pilot)
            if idx >= 0:
                combo_pilot.setCurrentIndex(idx)
            else:
                combo_pilot.addItem(pilot)
                combo_pilot.setCurrentText(pilot)
        elif pilot == "In attesa...":
            combo_pilot.addItem("In attesa...")
            combo_pilot.setCurrentText("In attesa...")
        else:
            combo_pilot.setCurrentIndex(0)

        combo_pilot.setStyleSheet("""
            QComboBox {
                background-color: #1a253c;
                color: #38bdf8;
                border: 1px solid #2a3b5c;
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: 700;
                font-size: 13px;
            }
            QComboBox:hover { border-color: #06b6d4; }
            QComboBox:focus { border: 1.5px solid #06b6d4; }
            QComboBox QAbstractItemView {
                background-color: #131b2e;
                color: #f8fafc;
                selection-background-color: #0891b2;
                border: 1px solid #23314f;
                padding: 4px;
            }
        """)
        combo_pilot.currentTextChanged.connect(lambda text, r=row, p=video_path: self._on_pilot_combo_changed(r, p, text))
        self.table_flights.setCellWidget(row, 3, combo_pilot)

        # Colonna 4: Vela / Colore
        item_glider = QTableWidgetItem(glider)
        item_glider.setForeground(QBrush(QColor("#06b6d4")))
        item_glider.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self.table_flights.setItem(row, 4, item_glider)

        # Colonna 5: Esito / Certezza
        if is_confirmed:
            self._set_certainty_badge(row, confidence)
        else:
            prog_bar = QProgressBar()
            prog_bar.setRange(0, 100)
            prog_bar.setValue(0)
            prog_bar.setFixedWidth(130)
            prog_bar.setFixedHeight(16)
            prog_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #23314f;
                    border-radius: 8px;
                    text-align: center;
                    background-color: #0b111e;
                    color: #94a3b8;
                    font-size: 10px;
                    font-weight: 700;
                }
                QProgressBar::chunk {
                    background-color: #06b6d4;
                    border-radius: 7px;
                }
            """)
            self.table_flights.setCellWidget(row, 5, prog_bar)

        # Colonna 6: Chiamata Radio
        item_phrases = QTableWidgetItem(phrases)
        item_phrases.setFlags(item_phrases.flags() ^ Qt.ItemFlag.ItemIsEditable)
        item_phrases.setForeground(QBrush(QColor("#cbd5e1")))
        self.table_flights.setItem(row, 6, item_phrases)

        # Colonna 7: Debriefing Button
        btn_watch = QPushButton("▶ Guarda")
        btn_watch.setStyleSheet("""
            QPushButton {
                padding: 5px 14px;
                font-weight: 700;
                font-size: 12px;
                background-color: #0891b2;
                color: #ffffff;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #06b6d4; }
            QPushButton:pressed { background-color: #0e7490; }
        """)
        btn_watch.clicked.connect(lambda _, p=video_path: self.open_debriefing_requested.emit(p))
        self.table_flights.setCellWidget(row, 7, btn_watch)
        self.table_flights.blockSignals(False)

    def _set_certainty_badge(self, row: int, confidence: float):
        self.table_flights.removeCellWidget(row, 5)
        pct = int(confidence * 100) if confidence <= 1.0 else int(confidence)
        if pct >= 85:
            text = f"🟢 {pct}% Certo"
            color = "#10b981"
        elif pct >= 65:
            text = f"🟡 {pct}% Probabile"
            color = "#f59e0b"
        else:
            text = f"🔴 {pct}% Incerto"
            color = "#f43f5e"

        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QBrush(QColor(color)))
        item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table_flights.setItem(row, 5, item)

    def update_clip_progress(self, video_path: str, curr_sec: float, total_sec: float):
        pct = int(min(100.0, (curr_sec / max(0.1, total_sec)) * 100.0)) if total_sec > 0 else 50
        for r in range(self.table_flights.rowCount()):
            item = self.table_flights.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == video_path:
                bar = self.table_flights.cellWidget(r, 5)
                if isinstance(bar, QProgressBar):
                    bar.setValue(pct)
                break

    def on_clip_analyzed(self, match: VideoPilotMatch):
        for r in range(self.table_flights.rowCount()):
            item = self.table_flights.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == match.video_path:
                self.table_flights.blockSignals(True)

                combo_pilot = self.table_flights.cellWidget(r, 3)
                if isinstance(combo_pilot, QComboBox):
                    combo_pilot.blockSignals(True)
                    idx = combo_pilot.findText(match.detected_pilot)
                    if idx >= 0:
                        combo_pilot.setCurrentIndex(idx)
                    else:
                        combo_pilot.addItem(match.detected_pilot)
                        combo_pilot.setCurrentText(match.detected_pilot)
                    combo_pilot.blockSignals(False)

                spin_volo = self.table_flights.cellWidget(r, 2)
                final_flight_num = match.flight_number
                if not final_flight_num or final_flight_num <= 0:
                    final_flight_num = self.calculate_auto_flight_number(match.detected_pilot, r)

                if isinstance(spin_volo, QSpinBox):
                    spin_volo.blockSignals(True)
                    spin_volo.setValue(final_flight_num)
                    spin_volo.blockSignals(False)

                glider_val = self.pilot_gliders.get(match.detected_pilot.lower(), "")
                g_item = QTableWidgetItem(glider_val)
                g_item.setForeground(QBrush(QColor("#38bdf8")))
                self.table_flights.setItem(r, 4, g_item)

                conf = getattr(match, "confidence", 1.0) or 1.0
                self._set_certainty_badge(r, conf)

                phr = " | ".join(match.matched_phrases) if match.matched_phrases else "—"
                self.table_flights.setItem(r, 6, QTableWidgetItem(phr))
                self.table_flights.blockSignals(False)

                sc = SidecarData(match.video_path)
                sc.pilot_name = match.detected_pilot
                sc.flight_number = final_flight_num
                sc.confidence = conf
                if glider_val:
                    sc.glider = glider_val
                if match.matched_phrases:
                    sc.radio_phrase = " | ".join(match.matched_phrases)
                sc.save()
                break

    def _on_flight_spin_changed(self, row: int, video_path: str, value: int):
        if not video_path or not os.path.exists(video_path):
            return
        sc = SidecarData(video_path)
        sc.flight_number = value
        sc.save()

    def _on_pilot_combo_changed(self, row: int, video_path: str, pilot_name: str):
        if not video_path or not os.path.exists(video_path):
            return
        pilot_name = pilot_name.strip()
        sc = SidecarData(video_path)
        sc.pilot_name = pilot_name
        sc.manual_override = True
        sc.confidence = 1.0

        glider_val = self.pilot_gliders.get(pilot_name.lower(), "")
        if glider_val:
            sc.glider = glider_val
            g_item = self.table_flights.item(row, 4)
            if g_item:
                g_item.setText(glider_val)
            else:
                self.table_flights.setItem(row, 4, QTableWidgetItem(glider_val))

        spin_volo = self.table_flights.cellWidget(row, 2)
        if isinstance(spin_volo, QSpinBox):
            auto_num = self.calculate_auto_flight_number(pilot_name, row)
            spin_volo.blockSignals(True)
            spin_volo.setValue(auto_num)
            spin_volo.blockSignals(False)
            sc.flight_number = auto_num

        sc.save()
        self._set_certainty_badge(row, 1.0)

    def _on_table_cell_edited(self, row: int, col: int):
        v_path = self.table_flights.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not v_path or not os.path.exists(v_path):
            return
        sc = SidecarData(v_path)
        if col == 4:
            sc.glider = self.table_flights.item(row, 4).text().strip()
            sc.save()

    def _on_row_double_clicked(self, row: int, col: int):
        v_path = self.table_flights.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if v_path and os.path.exists(v_path):
            self.open_debriefing_requested.emit(v_path)

    def get_flights_map_for_export(self) -> dict:
        flights_map = {}
        for r in range(self.table_flights.rowCount()):
            item_file = self.table_flights.item(r, 0)
            if not item_file:
                continue
            v_path = item_file.data(Qt.ItemDataRole.UserRole)
            p_combo = self.table_flights.cellWidget(r, 3)
            p_name = p_combo.currentText().strip() if isinstance(p_combo, QComboBox) else ""
            if not p_name or p_name in ["Da Assegnare", "In attesa..."]:
                continue

            spin_f = self.table_flights.cellWidget(r, 2)
            fl_num = spin_f.value() if isinstance(spin_f, QSpinBox) else 1

            key = (p_name, fl_num)
            if key not in flights_map:
                flights_map[key] = []
            flights_map[key].append(v_path)
        return flights_map

    def row_count(self) -> int:
        return self.table_flights.rowCount()
