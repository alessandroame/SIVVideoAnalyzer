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
from ui.components.glider_badge import GliderBadgeWidget

ARROW_UP_PATH, ARROW_DOWN_PATH = ensure_arrow_icons()

class FlightTableWidget(QWidget):
    """Componente autonomo per la gestione del Registro Voli Live."""
    back_to_config_requested = pyqtSignal()
    open_debriefing_requested = pyqtSignal(str)
    export_all_requested = pyqtSignal()
    reset_analysis_requested = pyqtSignal()
    inspect_wing_color_requested = pyqtSignal(str)

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

        # Indicatori di stato a 3 Fasi distinti
        self.lbl_badge_audio = QLabel("🎙️ Audio: 0/0")
        self.lbl_badge_audio.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; border: 1px solid #334155;")
        top.addWidget(self.lbl_badge_audio)

        self.lbl_badge_wing = QLabel("🪂 Vela: 0/0")
        self.lbl_badge_wing.setStyleSheet("background-color: #1e293b; color: #eab308; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; border: 1px solid #334155;")
        top.addWidget(self.lbl_badge_wing)

        self.lbl_badge_man = QLabel("🎯 Manovre: 0/0")
        self.lbl_badge_man.setStyleSheet("background-color: #1e293b; color: #a855f7; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; border: 1px solid #334155;")
        top.addWidget(self.lbl_badge_man)

        self.lbl_worker_status = QLabel("")
        self.lbl_worker_status.setStyleSheet("color: #38bdf8; font-weight: 600; font-size: 12px; margin-left: 6px;")
        top.addWidget(self.lbl_worker_status)

        self.progress_overall = QProgressBar()
        self.progress_overall.setFixedWidth(140)
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

        # Tabella Voli (8 Colonne Distinte per Fase)
        # 0: File Video (Stretch per adattarsi al restringimento)
        # 1: Data e Ora
        # 2: Volo N°
        # 3: Pilota Assegnato
        # 4: 🎙️ Analisi Pilota (compatta: radio check/chiamata)
        # 5: 🪂 Analisi Vela (badge compatto colori)
        # 6: 🎯 Manovre SIV (badge compatto)
        # 7: Debriefing (pulsante player)
        self.table_flights = QTableWidget(0, 8)
        self.table_flights.setHorizontalHeaderLabels([
            "File Video", "Data e Ora", "Volo N°", "Pilota Assegnato", "🎙️ Analisi Pilota", "🪂 Analisi Vela", "🎯 Manovre SIV", "Debriefing"
        ])
        self.table_flights.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_flights.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table_flights.verticalHeader().setDefaultSectionSize(42)
        self.table_flights.verticalHeader().setVisible(False)
        self.table_flights.setShowGrid(False)


        self.table_flights.cellChanged.connect(self._on_table_cell_edited)
        self.table_flights.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table_flights)

        hint = QLabel("💡 <b>Suggerimento:</b> Doppio clic su una riga per aprire il Debriefing. Puoi selezionare il Pilota dal menù o cliccare sui colori della vela per aprire la diagnostica.")
        hint.setStyleSheet("color: #64748b; font-size: 12px; margin-top: 2px;")
        layout.addWidget(hint)

    def set_session_info(self, title: str, pilots: list, gliders: dict):
        self.lbl_table_header.setText(title)
        self.known_pilots = list(pilots)
        self.pilot_gliders = dict(gliders)
        self.table_flights.setRowCount(0)

    def update_phases_status(self, audio_done: int, wing_done: int, man_done: int, total_clips: int):
        tot = max(1, total_clips)
        a_col = "#10b981" if audio_done >= tot else "#38bdf8"
        w_col = "#10b981" if wing_done >= tot else "#eab308"
        m_col = "#10b981" if man_done >= tot else "#a855f7"

        self.lbl_badge_audio.setText(f"🎙️ Audio: {audio_done}/{tot}")
        self.lbl_badge_audio.setStyleSheet(f"background-color: #1e293b; color: {a_col}; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; border: 1px solid #334155;")

        self.lbl_badge_wing.setText(f"🪂 Vela: {wing_done}/{tot}")
        self.lbl_badge_wing.setStyleSheet(f"background-color: #1e293b; color: {w_col}; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; border: 1px solid #334155;")

        self.lbl_badge_man.setText(f"🎯 Manovre: {man_done}/{tot}")
        self.lbl_badge_man.setStyleSheet(f"background-color: #1e293b; color: {m_col}; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px; border: 1px solid #334155;")

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

    def add_flight_row(self, video_path: str, pilot: str, flight_num: int, glider: str, phrases: str, is_confirmed: bool, confidence: float = 1.0, recorded_at: str = "", wing_colors: list = None):
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

        # Colonna 4: 🎙️ Analisi Pilota (Radio Check / Chiamata)
        if is_confirmed:
            self._set_audio_badge(row, confidence, phrases)
        else:
            prog_bar = QProgressBar()
            prog_bar.setRange(0, 100)
            prog_bar.setValue(0)
            prog_bar.setFixedWidth(100)
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
            self.table_flights.setCellWidget(row, 4, prog_bar)


        # Colonna 5: 🪂 Analisi Vela (Badge Cromatico)
        badge_glider = GliderBadgeWidget(glider, wing_colors)
        badge_glider.clicked.connect(lambda p=video_path: self.inspect_wing_color_requested.emit(p))
        self.table_flights.setCellWidget(row, 5, badge_glider)

        # Colonna 6: 🎯 Manovre SIV
        sc = SidecarData(video_path)
        ch_count = len(sc.chapters) if sc.chapters else 0
        if ch_count > 0:
            item_man = QTableWidgetItem(f"🟢 {ch_count} manovre")
            item_man.setForeground(QBrush(QColor("#10b981")))
        else:
            item_man = QTableWidgetItem("⚪ In attesa..." if not is_confirmed else "⚪ Nessuna")
            item_man.setForeground(QBrush(QColor("#94a3b8")))
        item_man.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_man.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        item_man.setFlags(item_man.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table_flights.setItem(row, 6, item_man)

        # Colonna 7: Debriefing Button
        btn_label = f"▶ Guarda ({ch_count})" if ch_count > 0 else "▶ Guarda"
        btn_watch = QPushButton(btn_label)
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

    def _set_audio_badge(self, row: int, confidence: float, radio_phrase: str = ""):
        self.table_flights.removeCellWidget(row, 4)
        pct = int(confidence * 100) if confidence <= 1.0 else int(confidence)
        if pct >= 75:
            text = f"🟢 Radio: {pct}%"
            color = "#10b981"
        elif pct >= 45:
            text = f"🟡 Radio: {pct}%"
            color = "#f59e0b"
        elif radio_phrase:
            text = "🟡 Radio debole"
            color = "#f59e0b"
        else:
            text = "⚪ Nessuna radio"
            color = "#94a3b8"

        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QBrush(QColor(color)))
        item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
        if radio_phrase:
            item.setToolTip(f"Frase radio rilevata:\n{radio_phrase}")
        self.table_flights.setItem(row, 4, item)

    def update_audio_result(self, video_path: str, confidence: float, radio_phrase: str, detected_pilot: str):
        for r in range(self.table_flights.rowCount()):
            item = self.table_flights.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == video_path:
                self._set_audio_badge(r, confidence, radio_phrase)
                break

    def update_wing_result(self, video_path: str, wing_colors: list, confidence: float, detected_pilot: str):
        for r in range(self.table_flights.rowCount()):
            item = self.table_flights.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == video_path:
                w_badge = self.table_flights.cellWidget(r, 5)
                glider_val = self.pilot_gliders.get(detected_pilot.lower(), "") if detected_pilot else ""
                if isinstance(w_badge, GliderBadgeWidget):
                    w_badge.set_data(glider_val, wing_colors)
                else:
                    new_badge = GliderBadgeWidget(glider_val, wing_colors)
                    new_badge.clicked.connect(lambda p=video_path: self.inspect_wing_color_requested.emit(p))
                    self.table_flights.setCellWidget(r, 5, new_badge)
                break

    def update_clip_progress(self, video_path: str, curr_sec: float, total_sec: float):
        pct = int(min(100.0, (curr_sec / max(0.1, total_sec)) * 100.0)) if total_sec > 0 else 50
        for r in range(self.table_flights.rowCount()):
            item = self.table_flights.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == video_path:
                bar = self.table_flights.cellWidget(r, 4)
                if isinstance(bar, QProgressBar):
                    bar.setValue(pct)
                break

    def update_maneuver_progress(self, video_path: str, status_text: str, percent: int):
        for r in range(self.table_flights.rowCount()):
            item = self.table_flights.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == video_path:
                # Aggiorna Colonna 6: Manovre SIV
                sc = SidecarData(video_path)
                count = len(sc.chapters) if sc.chapters else 0
                if percent < 100:
                    it_man = QTableWidgetItem(f"⏳ {percent}%")
                    it_man.setForeground(QBrush(QColor("#a855f7")))
                    it_man.setToolTip(f"Rilevamento in corso: {status_text}")
                elif count > 0:
                    it_man = QTableWidgetItem(f"🟢 {count} manovre")
                    it_man.setForeground(QBrush(QColor("#10b981")))
                    it_man.setToolTip(f"{count} manovre rilevate")
                else:
                    it_man = QTableWidgetItem("⚪ Nessuna")
                    it_man.setForeground(QBrush(QColor("#94a3b8")))
                it_man.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it_man.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                it_man.setFlags(it_man.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table_flights.setItem(r, 6, it_man)

                # Aggiorna Colonna 7: Tasto Debriefing
                btn = self.table_flights.cellWidget(r, 7)
                if isinstance(btn, QPushButton):
                    btn.setText(f"▶ Guarda ({count})" if count > 0 else "▶ Guarda")
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
                w_badge = self.table_flights.cellWidget(r, 5)
                w_colors = getattr(match, "wing_colors", []) or []
                if isinstance(w_badge, GliderBadgeWidget):
                    w_badge.set_data(glider_val, w_colors)
                else:
                    new_badge = GliderBadgeWidget(glider_val, w_colors)
                    new_badge.clicked.connect(lambda p=match.video_path: self.inspect_wing_color_requested.emit(p))
                    self.table_flights.setCellWidget(r, 5, new_badge)

                phr = " | ".join(match.matched_phrases) if match.matched_phrases else ""
                self._set_audio_badge(r, match.audio_confidence if match.audio_confidence > 0 else match.confidence, phr)
                self.table_flights.blockSignals(False)

                sc = SidecarData(match.video_path)
                sc.pilot_name = match.detected_pilot
                sc.flight_number = final_flight_num
                sc.confidence = match.confidence
                sc.audio_confidence = match.audio_confidence
                sc.wing_confidence = match.wing_confidence
                if glider_val:
                    sc.glider = glider_val
                if match.matched_phrases:
                    sc.radio_phrase = phr
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
            w_badge = self.table_flights.cellWidget(row, 5)
            if isinstance(w_badge, GliderBadgeWidget):
                w_badge.set_data(glider_val, sc.wing_colors)
            else:
                new_b = GliderBadgeWidget(glider_val, sc.wing_colors)
                new_b.clicked.connect(lambda p=video_path: self.inspect_wing_color_requested.emit(p))
                self.table_flights.setCellWidget(row, 5, new_b)

        spin_volo = self.table_flights.cellWidget(row, 2)
        if isinstance(spin_volo, QSpinBox):
            auto_num = self.calculate_auto_flight_number(pilot_name, row)
            spin_volo.blockSignals(True)
            spin_volo.setValue(auto_num)
            spin_volo.blockSignals(False)
            sc.flight_number = auto_num

        sc.save()
        self._set_audio_badge(row, 1.0, "Assegnato manualmente dall'istruttore")

    def _on_table_cell_edited(self, row: int, col: int):
        v_path = self.table_flights.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if not v_path or not os.path.exists(v_path):
            return
        sc = SidecarData(v_path)
        if col == 5:
            sc.glider = self.table_flights.item(row, 5).text().strip()
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
