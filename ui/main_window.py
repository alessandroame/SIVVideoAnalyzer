import os
import glob
import time
import json
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QMessageBox, QProgressBar,
    QStackedWidget, QTextEdit, QGroupBox, QFrame, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings

from core.audio_extractor import extract_audio
from core.transcriber import SIVTranscriber
from core.pilot_detector import PilotDetector, VideoPilotMatch
from core.file_sorter import FileSorter
from core.maneuver_detector import ManeuverDetector
from core.manifest_manager import PilotInfo, SivCourseManifest
from core.flight_grouper import FlightGrouper, SIVFlight, FlightClipInfo
from ui.step2_review_view import Step2ReviewView
from ui.step3_chapters_view import ChaptersView

class WorkerThread(QThread):
    progress_signal = pyqtSignal(str, int)
    clip_analyzed_signal = pyqtSignal(object) # Emette il VideoPilotMatch appena analizzato
    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)
    cancelled_signal = pyqtSignal()

    def __init__(self, task_fn, *args, **kwargs):
        super().__init__()
        self.task_fn = task_fn
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False

    def request_cancel(self):
        self._is_cancelled = True

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self):
        try:
            res = self.task_fn(self.progress_signal, self.clip_analyzed_signal, self.is_cancelled, *self.args, **self.kwargs)
            if self._is_cancelled:
                self.cancelled_signal.emit()
            else:
                self.finished_signal.emit(res)
        except Exception as e:
            if self._is_cancelled:
                self.cancelled_signal.emit()
            else:
                import traceback
                self.error_signal.emit(f"{str(e)}\n\n{traceback.format_exc()}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SIV Video Analyzer & Manager - Didattica per Volo")
        self.resize(1200, 800)

        self.transcriber = SIVTranscriber(model_size="base")
        self.maneuver_detector = ManeuverDetector()
        self.flight_grouper = FlightGrouper()
        
        self.detected_matches = []
        self.pilots_info: list[PilotInfo] = []
        self.pilot_flights: dict[str, list[SIVFlight]] = {} # pilot_name -> [SIVFlight]
        self.current_pilot = None
        self.current_flight = None
        self.settings = QSettings("SIVVideoAnalyzer", "Settings")

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Wizard Step Header / Stepper indicator a 4 FASI
        self.header_frame = QFrame()
        self.header_frame.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        h_layout = QHBoxLayout(self.header_frame)
        h_layout.setContentsMargins(15, 5, 15, 5)

        self.lbl_step1 = QLabel("1. Parametri")
        self.lbl_step2 = QLabel("2. Analisi Video")
        self.lbl_step3 = QLabel("3. Revisione Voli")
        self.lbl_step4 = QLabel("4. Debriefing")

        h_layout.addWidget(self.lbl_step1)
        h_layout.addWidget(QLabel(" ➔ "))
        h_layout.addWidget(self.lbl_step2)
        h_layout.addWidget(QLabel(" ➔ "))
        h_layout.addWidget(self.lbl_step3)
        h_layout.addWidget(QLabel(" ➔ "))
        h_layout.addWidget(self.lbl_step4)
        h_layout.addStretch()

        btn_open_replay = QPushButton("📂 Apri Sessione Esistente (Replay)")
        btn_open_replay.setStyleSheet("""
            QPushButton {
                background-color: #0f766e;
                color: white;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #115e59;
            }
        """)
        btn_open_replay.clicked.connect(self.open_existing_replay_folder)
        h_layout.addWidget(btn_open_replay)

        main_layout.addWidget(self.header_frame)

        # Stacked Widget per le 4 pagine del Wizard
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # Step 1: Acquisizione Parametri
        self.step1_widget = QWidget()
        self.init_step1_widget()
        self.stacked_widget.addWidget(self.step1_widget)

        # Step 2: Analisi Video (Nuova Pagina Dedicata)
        self.step2_analysis_widget = QWidget()
        self.init_step2_analysis_widget()
        self.stacked_widget.addWidget(self.step2_analysis_widget)

        # Step 3: Tabella Revisione a Schermo Intero (con Voli)
        self.step3_widget = Step2ReviewView()
        self.step3_widget.confirmed_signal.connect(self.on_review_confirmed_enter_debriefing)
        self.step3_widget.back_signal.connect(self.on_review_back_clicked)
        self.stacked_widget.addWidget(self.step3_widget)

        # Step 4: Hub Debriefing & Player Voli
        self.step4_widget = ChaptersView()
        self.step4_widget.pilot_selected_signal.connect(self.on_hub_pilot_selected)
        self.step4_widget.flight_selected_signal.connect(self.on_hub_flight_selected)
        self.step4_widget.save_changes_signal.connect(self.save_flight_changes)
        self.step4_widget.back_signal.connect(lambda: self.go_to_step(2))
        self.stacked_widget.addWidget(self.step4_widget)

        # Barra di stato discreta in basso (solo per messaggi generali)
        self.status_box = QHBoxLayout()
        self.status_box.setContentsMargins(4, 4, 4, 4)
        self.status_label = QLabel("Pronto.")
        self.status_label.setStyleSheet("font-size: 12px; color: #94a3b8;")
        self.status_box.addWidget(self.status_label, stretch=1)
        main_layout.addLayout(self.status_box)

        self.go_to_step(0)

        self.go_to_step(0)

    def update_stepper_style(self, current_step: int):
        active_style = "color: #38bdf8; font-weight: bold; text-decoration: underline;"
        inactive_style = "color: #94a3b8; font-weight: normal;"

        self.lbl_step1.setStyleSheet(active_style if current_step == 0 else inactive_style)
        self.lbl_step2.setStyleSheet(active_style if current_step == 1 else inactive_style)
        self.lbl_step3.setStyleSheet(active_style if current_step == 2 else inactive_style)
        self.lbl_step4.setStyleSheet(active_style if current_step == 3 else inactive_style)

    def go_to_step(self, step_idx: int):
        self.stacked_widget.setCurrentIndex(step_idx)
        self.update_stepper_style(step_idx)

    def init_step1_widget(self):
        layout = QVBoxLayout(self.step1_widget)
        layout.setSpacing(14)
        layout.setContentsMargins(15, 15, 15, 15)

        # Selezione Cartella Sorgente Video
        box_input = QGroupBox("1. Dove si trovano i video del SIV? (Scheda SD o Cartella)")
        box_input.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        l_in = QHBoxLayout(box_input)
        self.txt_source_dir = QLineEdit()
        self.txt_source_dir.setPlaceholderText("Es. E:\\ o D:\\Video SIV...")
        self.txt_source_dir.setStyleSheet("padding: 8px; font-size: 13px;")
        l_in.addWidget(self.txt_source_dir)
        btn_browse_src = QPushButton("Sfoglia Cartella...")
        btn_browse_src.setStyleSheet("padding: 8px 16px; font-size: 13px; font-weight: 500;")
        btn_browse_src.clicked.connect(self.browse_source_dir)
        l_in.addWidget(btn_browse_src)
        layout.addWidget(box_input)

        # Gestione Piloti del Corso con Modello Vela e Colori
        box_pilots = QGroupBox("2. Piloti del Corso (Nome e Colore Vela per facilitare il debriefing)")
        box_pilots.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        l_pilots = QVBoxLayout(box_pilots)

        self.table_pilots = QTableWidget(0, 3)
        self.table_pilots.setHorizontalHeaderLabels(["Nome Pilota", "Vela (es. Rush 6, Mentor)", "Colori Vela (es. Rosso/Nero)"])
        self.table_pilots.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_pilots.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_pilots.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_pilots.setStyleSheet("font-size: 13px;")
        l_pilots.addWidget(self.table_pilots)

        pilot_btn_layout = QHBoxLayout()
        btn_add_p = QPushButton("➕ Aggiungi Pilota")
        btn_add_p.setStyleSheet("padding: 6px 14px; font-size: 13px;")
        btn_add_p.clicked.connect(self.add_pilot_row)
        pilot_btn_layout.addWidget(btn_add_p)

        btn_del_p = QPushButton("➖ Rimuovi Selezionato")
        btn_del_p.setStyleSheet("padding: 6px 14px; font-size: 13px;")
        btn_del_p.clicked.connect(self.remove_pilot_row)
        pilot_btn_layout.addWidget(btn_del_p)
        pilot_btn_layout.addStretch()

        l_pilots.addLayout(pilot_btn_layout)
        layout.addWidget(box_pilots, stretch=1)

        # Cartella di Output e Modalità Modello Whisper (Compatti e Chiari)
        row_config = QHBoxLayout()

        box_output = QGroupBox("3. Dove salvare la sessione per i debriefing?")
        box_output.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        l_out = QHBoxLayout(box_output)
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setText(os.path.abspath("output_siv"))
        self.txt_output_dir.setStyleSheet("padding: 8px; font-size: 13px;")
        l_out.addWidget(self.txt_output_dir)
        btn_browse_out = QPushButton("Sfoglia...")
        btn_browse_out.setStyleSheet("padding: 8px 16px; font-size: 13px;")
        btn_browse_out.clicked.connect(self.browse_output_dir)
        l_out.addWidget(btn_browse_out)
        row_config.addWidget(box_output, stretch=3)

        box_model = QGroupBox("Modalità Trascrizione")
        box_model.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; }")
        l_model = QHBoxLayout(box_model)
        self.combo_model = QComboBox()
        self.combo_model.addItem("⚡ Ultra Rapida (Consigliata tra i voli)", "base")
        self.combo_model.addItem("🎯 Approfondita (Per fine giornata)", "small")
        self.combo_model.setStyleSheet("padding: 8px; font-size: 13px;")
        l_model.addWidget(self.combo_model)
        row_config.addWidget(box_model, stretch=2)

        layout.addLayout(row_config)

        # Pulsante di Azione Primario e Gestione Cache
        btn_action_layout = QHBoxLayout()

        self.btn_clear_cache = QPushButton("🗑 Svuota Cache")
        self.btn_clear_cache.setToolTip("Elimina le trascrizioni memorizzate per rieseguire l'analisi da zero")
        self.btn_clear_cache.setStyleSheet("""
            QPushButton {
                background-color: #475569; 
                color: #f1f5f9; 
                font-size: 13px; 
                padding: 12px 18px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #64748b;
            }
        """)
        self.btn_clear_cache.clicked.connect(self.clear_cache)
        btn_action_layout.addWidget(self.btn_clear_cache)

        self.btn_detect_pilots = QPushButton("🚀 AVVIA ANALISI VIDEO E RICONOSCIMENTO PILOTI ➡")
        self.btn_detect_pilots.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; 
                color: white; 
                font-weight: bold; 
                font-size: 15px; 
                padding: 14px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_detect_pilots.clicked.connect(self.start_pilot_detection)
        btn_action_layout.addWidget(self.btn_detect_pilots, stretch=1)

        layout.addLayout(btn_action_layout)

    def init_step2_analysis_widget(self):
        """Nuova Schermata Dedicata: Monitoraggio Analisi a Stress Zero"""
        layout = QVBoxLayout(self.step2_analysis_widget)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Scheda Riepilogo Impostazioni di Lancio
        self.card_analysis_config = QFrame()
        self.card_analysis_config.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border-radius: 8px;
                padding: 14px 18px;
                border: 1px solid #334155;
            }
            QLabel {
                color: #f8fafc;
                font-size: 13px;
            }
        """)
        l_card = QVBoxLayout(self.card_analysis_config)
        self.lbl_analysis_title = QLabel("<h3 style='margin:0; color:#38bdf8;'>⚙ Analisi Video in Corso...</h3>")
        self.lbl_analysis_summary = QLabel("Configurazione: Inizializzazione...")
        self.lbl_analysis_summary.setStyleSheet("color: #cbd5e1; font-size: 13px; margin-top: 4px;")
        l_card.addWidget(self.lbl_analysis_title)
        l_card.addWidget(self.lbl_analysis_summary)
        layout.addWidget(self.card_analysis_config)

        # Sezione Centrale: Mega Progress Bar & Stato
        progress_box = QFrame()
        progress_box.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border-radius: 8px;
                padding: 18px;
                border: 1px solid #334155;
            }
        """)
        l_prog = QVBoxLayout(progress_box)
        l_prog.setSpacing(10)

        self.lbl_analysis_task = QLabel("Inizio scansione file video...")
        self.lbl_analysis_task.setStyleSheet("font-size: 15px; font-weight: bold; color: #f1f5f9;")
        l_prog.addWidget(self.lbl_analysis_task)

        self.analysis_progress_bar = QProgressBar()
        self.analysis_progress_bar.setValue(0)
        self.analysis_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #475569;
                border-radius: 6px;
                text-align: center;
                height: 32px;
                font-size: 14px;
                font-weight: bold;
                color: #ffffff;
                background-color: #1e293b;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 5px;
            }
        """)
        l_prog.addWidget(self.analysis_progress_bar)

        self.lbl_analysis_eta = QLabel("⏱ Calcolo tempo residuo...")
        self.lbl_analysis_eta.setStyleSheet("font-size: 13px; color: #38bdf8; font-weight: bold;")
        l_prog.addWidget(self.lbl_analysis_eta)

        layout.addWidget(progress_box)

        # Log Eventi Rilevati (Solo ciò che conta)
        lbl_log = QLabel("<b>Manovre e Piloti Riconosciuti durante l'ascolto radio:</b>")
        lbl_log.setStyleSheet("font-size: 13px; color: #cbd5e1;")
        layout.addWidget(lbl_log)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #090d16;
                color: #e2e8f0;
                font-family: Consolas, monospace;
                font-size: 13px;
                border-radius: 6px;
                border: 1px solid #1e293b;
                padding: 10px;
            }
        """)
        layout.addWidget(self.log_text, stretch=1)

        # Pulsanti in Basso: Interrompi o Passa subito a Revisione
        bottom_bar = QHBoxLayout()

        self.btn_cancel_task = QPushButton("⏹ Interrompi Analisi")
        self.btn_cancel_task.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; 
                color: white; 
                font-weight: bold; 
                font-size: 13px;
                padding: 10px 20px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
        """)
        self.btn_cancel_task.clicked.connect(self.cancel_current_task)
        bottom_bar.addWidget(self.btn_cancel_task)

        bottom_bar.addStretch()

        self.btn_view_review_now = QPushButton("📋 Vedi Tabella Revisione (0 clip) ➡")
        self.btn_view_review_now.setStyleSheet("""
            QPushButton {
                background-color: #0f766e; 
                color: white; 
                font-weight: bold; 
                font-size: 14px;
                padding: 10px 22px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #115e59;
            }
        """)
        self.btn_view_review_now.clicked.connect(lambda: self.go_to_step(2))
        bottom_bar.addWidget(self.btn_view_review_now)

        layout.addLayout(bottom_bar)

    def add_pilot_row(self, nome="", vela="", colore=""):
        row = self.table_pilots.rowCount()
        self.table_pilots.insertRow(row)
        self.table_pilots.setItem(row, 0, QTableWidgetItem(nome))
        self.table_pilots.setItem(row, 1, QTableWidgetItem(vela))
        self.table_pilots.setItem(row, 2, QTableWidgetItem(colore))

    def remove_pilot_row(self):
        current_row = self.table_pilots.currentRow()
        if current_row >= 0:
            self.table_pilots.removeRow(current_row)
            self.save_settings()

    def get_pilots_from_table(self) -> list[PilotInfo]:
        pilots = []
        for r in range(self.table_pilots.rowCount()):
            nome_item = self.table_pilots.item(r, 0)
            vela_item = self.table_pilots.item(r, 1)
            colore_item = self.table_pilots.item(r, 2)
            nome = nome_item.text().strip() if nome_item else ""
            if nome:
                vela = vela_item.text().strip() if vela_item else ""
                colore = colore_item.text().strip() if colore_item else ""
                pilots.append(PilotInfo(id=nome.lower().replace(" ", "_"), nome=nome, vela_marca_modello=vela, colori_vela=colore))
        return pilots

    def clear_cache(self):
        temp_dir = "temp"
        if not os.path.exists(temp_dir):
            QMessageBox.information(self, "Cache Vuota", "Nessun file di cache presente.")
            return

        cache_files = glob.glob(os.path.join(temp_dir, "*_cache.json")) + glob.glob(os.path.join(temp_dir, "*.wav"))
        if not cache_files:
            QMessageBox.information(self, "Cache Vuota", "La cache delle trascrizioni è già vuota.")
            return

        reply = QMessageBox.question(
            self,
            "Svuota Cache",
            f"Trovati {len(cache_files)} file di trascrizione in cache.\nVuoi eliminarli per forzare una nuova trascrizione completa?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = 0
            for f in cache_files:
                try:
                    os.remove(f)
                    count += 1
                except Exception as e:
                    self.log(f"Errore rimozione {f}: {e}")
            self.log(f"<b>Cache svuotata:</b> rimossi {count} file temporanei.")
            QMessageBox.information(self, "Cache Svuotata", f"Eliminati con successo {count} file di cache.")

    def log(self, msg: str):
        self.log_text.append(msg)

    def on_model_changed(self):
        m = self.combo_model.currentData() or "base"
        self.transcriber.set_model_size(m)
        self.save_settings()

    def load_settings(self):
        saved_src = self.settings.value("source_dir", "")
        if saved_src and os.path.exists(saved_src):
            self.txt_source_dir.setText(saved_src)

        saved_out = self.settings.value("output_dir", "")
        if saved_out:
            self.txt_output_dir.setText(saved_out)

        saved_model = self.settings.value("whisper_model", "base")
        idx = self.combo_model.findData(saved_model)
        if idx >= 0:
            self.combo_model.setCurrentIndex(idx)
        self.transcriber.set_model_size(saved_model)

        # Carica tabella piloti
        pilots_json = self.settings.value("pilots_json", "")
        self.table_pilots.setRowCount(0)
        if pilots_json:
            try:
                p_list = json.loads(pilots_json)
                for p in p_list:
                    self.add_pilot_row(p.get('nome', ''), p.get('vela', ''), p.get('colore', ''))
            except Exception:
                pass

        if self.table_pilots.rowCount() == 0:
            # Fallback su vecchi settings
            old_pilots = self.settings.value("pilots", "")
            if old_pilots:
                for p in old_pilots.split(","):
                    if p.strip():
                        self.add_pilot_row(p.strip(), "", "")

        # Collega i segnali di salvataggio automatico DOPO il caricamento
        self.txt_source_dir.textChanged.connect(self.save_settings)
        self.txt_output_dir.textChanged.connect(self.save_settings)
        self.combo_model.currentIndexChanged.connect(self.on_model_changed)
        self.table_pilots.itemChanged.connect(lambda: self.save_settings())

    def save_settings(self):
        self.settings.setValue("source_dir", self.txt_source_dir.text().strip())
        self.settings.setValue("output_dir", self.txt_output_dir.text().strip())
        self.settings.setValue("whisper_model", self.combo_model.currentData() or "base")

        # Salva piloti della tabella in formato JSON
        p_data = []
        for r in range(self.table_pilots.rowCount()):
            n = self.table_pilots.item(r, 0)
            v = self.table_pilots.item(r, 1)
            c = self.table_pilots.item(r, 2)
            if n and n.text().strip():
                p_data.append({
                    'nome': n.text().strip(),
                    'vela': v.text().strip() if v else '',
                    'colore': c.text().strip() if c else ''
                })
        self.settings.setValue("pilots_json", json.dumps(p_data))
        self.settings.sync()

    def closeEvent(self, event):
        if hasattr(self, 'worker') and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Elaborazione in corso",
                "Un'elaborazione video/audio è attualmente in corso.\nVuoi interromperla e chiudere l'applicazione?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.worker.request_cancel()
                self.worker.wait(2000)
                self.save_settings()
                event.accept()
            else:
                event.ignore()
                return

        self.save_settings()
        super().closeEvent(event)

    def browse_source_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella video sorgente", self.txt_source_dir.text().strip() or "")
        if d:
            self.txt_source_dir.setText(d)
            self.save_settings()

    def browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella di destinazione", self.txt_output_dir.text().strip() or "")
        if d:
            self.txt_output_dir.setText(d)
            self.save_settings()

    def start_pilot_detection(self):
        self.save_settings()
        src = self.txt_source_dir.text().strip()
        if not src or not os.path.exists(src):
            QMessageBox.warning(self, "Attenzione", "Seleziona una cartella sorgente valida.")
            return

        self.pilots_info = self.get_pilots_from_table()
        pilot_names = [p.nome for p in self.pilots_info]

        video_extensions = {
            ".mp4", ".mov", ".avi", ".mkv", 
            ".mts", ".m2ts", ".mxf", ".ts",
            ".wmv", ".flv", ".webm"
        }
        
        video_files = []
        for root, _, files in os.walk(src):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in video_extensions:
                    video_files.append(os.path.join(root, file))

        video_files = sorted(list(set(video_files)))

        if not video_files:
            QMessageBox.warning(self, "Nessun video", "Nessun file video trovato nella cartella specificata (inclusi formati Sony .MTS/.MXF/MP4).")
            return

        # Configura il riepilogo nella pagina di Analisi (Step 2)
        mode_name = self.combo_model.currentText()
        summary_text = (
            f"<b>Sorgente:</b> {src} &nbsp;|&nbsp; <b>Clip trovate:</b> {len(video_files)}<br>"
            f"<b>Modalità:</b> {mode_name} &nbsp;|&nbsp; <b>Piloti:</b> {', '.join(pilot_names) if pilot_names else 'Tutti'}"
        )
        self.lbl_analysis_summary.setText(summary_text)
        self.lbl_analysis_task.setText("Preparazione trascrizione audio...")
        self.lbl_analysis_eta.setText("⏱ Calcolo tempo residuo...")
        self.analysis_progress_bar.setValue(0)
        self.log_text.clear()
        self.btn_cancel_task.setEnabled(True)

        # Transizione automatica alla pagina di Analisi (Step 2)
        self.go_to_step(1)

        # Reset della tabella di Revisione (Step 3) per accogliere le clip in tempo reale
        self.step3_widget.reset_data(pilots_list=pilot_names)

        def task(progress_sig, clip_sig, is_cancelled):
            from core.audio_extractor import get_video_creation_time
            detector = PilotDetector(pilots_list=pilot_names, transcriber=self.transcriber)
            matches = []
            total = len(video_files)
            start_wall_time = time.time()
            last_eta_str = ""

            # Tracciamento dinamico per il calcolo progressivo del volo di ciascun pilota
            pilot_last_flight = {} # pilot -> ultimo flight_number
            pilot_last_time = {}   # pilot -> ultimo creation_time + duration

            for i, vf in enumerate(video_files):
                if is_cancelled():
                    progress_sig.emit("Operazione interrotta dall'utente.", 0)
                    return matches

                fname = os.path.basename(vf)
                base_percent = (i / total) * 100.0
                file_slice = 100.0 / total

                eta_display = f" | {last_eta_str}" if last_eta_str else ""
                progress_sig.emit(
                    f"Ascolto comunicazioni radio... Clip {i+1} di {total} ({fname}){eta_display}",
                    int(base_percent)
                )

                def on_file_progress(curr_sec, dur_sec):
                    nonlocal last_eta_str
                    elapsed = time.time() - start_wall_time
                    if dur_sec > 0:
                        curr_file_pct = min(1.0, curr_sec / dur_sec)
                        overall_pct = base_percent + (curr_file_pct * file_slice)
                    else:
                        overall_pct = base_percent

                    fraction_done = max(0.001, overall_pct / 100.0)
                    if elapsed > 1.5 and overall_pct > 1.0:
                        est_total = elapsed / fraction_done
                        remaining = max(0.0, est_total - elapsed)
                        m_rem = int(remaining // 60)
                        s_rem = int(remaining % 60)
                        last_eta_str = f"⏱ Circa {m_rem:02d}m {s_rem:02d}s rimanenti" if remaining > 2 else "⏱ Quasi completato..."

                    eta_display = f" | {last_eta_str}" if last_eta_str else ""
                    progress_sig.emit(
                        f"Ascolto comunicazioni radio... Clip {i+1} di {total} ({fname}){eta_display}",
                        int(overall_pct)
                    )

                m = detector.identify_pilot_from_audio(
                    vf, 
                    progress_callback=on_file_progress,
                    is_cancelled_callback=is_cancelled
                )
                if is_cancelled():
                    return matches

                # Calcolo del Numero di Volo per questa clip
                p = m.detected_pilot
                curr_t = get_video_creation_time(vf)
                prev_t = pilot_last_time.get(p, 0.0)
                prev_f = pilot_last_flight.get(p, 0)

                if m.flight_number is not None:
                    # Riconosciuto da chiamata radio esplicita
                    f_num = m.flight_number
                else:
                    if prev_f == 0:
                        f_num = 1
                    else:
                        gap = max(0.0, curr_t - prev_t) if prev_t > 0 else 9999.0
                        if gap > 1200.0:  # > 20 min -> Nuovo volo
                            f_num = prev_f + 1
                        else:             # <= 20 min -> Stesso volo (multi-clip)
                            f_num = prev_f

                m.flight_number = f_num
                pilot_last_flight[p] = f_num
                pilot_last_time[p] = curr_t + m.duration

                matches.append(m)

                # Emette la clip analizzata in TEMPO REALE verso la UI di revisione
                clip_sig.emit(m)

                # Notifica nel log l'avvenuto riconoscimento del pilota e del volo
                detected_str = f"→ {fname}: Riconosciuto <b>{m.detected_pilot}</b> (Volo {f_num})"
                if m.matched_phrases:
                    detected_str += f" - radio: <i>'{m.matched_phrases[0]}'</i>"
                progress_sig.emit(detected_str, int((i + 1) / total * 100.0))

            total_elapsed = int(time.time() - start_wall_time)
            progress_sig.emit(f"Riconoscimento completato in {total_elapsed // 60:02d}m {total_elapsed % 60:02d}s!", 100)
            return matches

        self.worker = WorkerThread(task)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.clip_analyzed_signal.connect(self.on_clip_analyzed_live)
        self.worker.finished_signal.connect(self.on_pilots_detected)
        self.worker.cancelled_signal.connect(self.on_task_cancelled)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def on_clip_analyzed_live(self, match):
        """Riceve in tempo reale ogni clip appena analizzata e la inserisce subito nella tabella di Revisione."""
        self.step3_widget.add_clip_match(match)
        count = self.step3_widget.table.rowCount()
        self.btn_view_review_now.setText(f"📋 Vedi Tabella Revisione ({count} clip pronte) ➡")

    def cancel_current_task(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Conferma Interruzione",
                "Sei sicuro di voler interrompere l'elaborazione in corso?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            self.lbl_analysis_task.setText("Interruzione in corso...")
            self.btn_cancel_task.setEnabled(False)
            self.worker.request_cancel()

    def on_task_cancelled(self):
        self.btn_cancel_task.setEnabled(True)
        self.btn_detect_pilots.setEnabled(True)
        self.lbl_analysis_task.setText("Elaborazione interrotta dall'utente.")
        self.log("<b>Elaborazione interrotta dall'utente.</b>")
        # Riporta allo Step 1 (Parametri)
        self.go_to_step(0)

    def on_progress(self, msg, val):
        if msg.startswith("→"):
            # È un evento chiave (pilota riconosciuto): lo stampiamo nel log
            self.log(msg)
        else:
            # È lo stato del progresso: lo mostriamo nella label di task ed estraiamo l'ETA
            if " | " in msg:
                task_part, eta_part = msg.split(" | ", 1)
                self.lbl_analysis_task.setText(task_part)
                self.lbl_analysis_eta.setText(eta_part)
            else:
                self.lbl_analysis_task.setText(msg)
        self.analysis_progress_bar.setValue(val)

    def on_pilots_detected(self, matches):
        self.btn_detect_pilots.setEnabled(True)
        self.detected_matches = self.step3_widget.matches if self.step3_widget.matches else matches
        # Passa allo Step 3 (Revisione Voli)
        self.go_to_step(2)
        self.status_label.setText("Tutte le clip sono state analizzate. Verifica e clicca 'Entra nel Debriefing'.")

    def on_review_back_clicked(self):
        """Se l'analisi è ancora in corso, torna alla schermata di analisi; altrimenti torna ai parametri."""
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.go_to_step(1)
        else:
            self.go_to_step(0)

    def on_review_confirmed_enter_debriefing(self):
        """
        Salva i dati dell'output portatile (manifest e cartelle volo) ed entra
        immediatamente nello Step 3 (Live Debriefing) SENZA attendere alcun montaggio video!
        """
        out_dir = self.txt_output_dir.text().strip() or "output_siv"
        os.makedirs(out_dir, exist_ok=True)

        # 1. Salva il manifest del corso
        manifest = SivCourseManifest(
            nome_corso=f"Corso SIV - {time.strftime('%B %Y')}",
            data_inizio=time.strftime("%Y-%m-%d"),
            piloti=self.pilots_info
        )
        manifest.save(out_dir)

        # 2. Raggruppa i video per pilota e per numero di volo
        pilot_groups = {}
        for m in self.detected_matches:
            pilot_groups.setdefault(m.detected_pilot, []).append(m)

        self.pilot_flights = {}
        grouper = FlightGrouper()

        for pilot_name, matches in pilot_groups.items():
            # Raggruppa in base al volo selezionato dall'utente
            by_flight_num = {}
            for m in matches:
                f_num = getattr(m, 'flight_number', 1) or 1
                by_flight_num.setdefault(f_num, []).append(m)

            flights = []
            for f_num in sorted(by_flight_num.keys()):
                m_list = by_flight_num[f_num]
                f_objs = grouper.group_pilot_matches_into_flights(pilot_name, m_list)
                if f_objs:
                    f = f_objs[0]
                    f.flight_number = f_num
                    f.flight_id = f"Volo_{f_num:02d}"
                    flights.append(f)

            self.pilot_flights[pilot_name] = flights

            # Salva i metadati e capitoli nella cartella del volo dell'output per portabilità
            pilot_dir = os.path.join(out_dir, pilot_name)
            for f in flights:
                flight_dir = os.path.join(pilot_dir, f.flight_id)
                f.save_to_folder(flight_dir)

        # 3. Prepara lo Step 3
        pilots_with_flights = list(self.pilot_flights.keys())
        if not pilots_with_flights:
            QMessageBox.warning(self, "Attenzione", "Nessun pilota con voli disponibile.")
            return

        # Popola la lista piloti formattata (con vela e colore)
        p_info_map = {p.nome: p for p in self.pilots_info}
        display_pilots = []
        for p_name in pilots_with_flights:
            if p_name in p_info_map:
                p = p_info_map[p_name]
                desc = f"{p.nome}"
                if p.vela_marca_modello:
                    desc += f" [{p.vela_marca_modello}"
                    if p.colori_vela:
                        desc += f" - {p.colori_vela}"
                    desc += "]"
                display_pilots.append((p_name, desc))
            else:
                display_pilots.append((p_name, p_name))

        first_pilot = pilots_with_flights[0]
        self.step4_widget.set_pilots_list(display_pilots, current_pilot=first_pilot)
        self.go_to_step(3)
        self.load_pilot_flights_into_hub(first_pilot)

    def on_hub_pilot_selected(self, pilot_name: str):
        self.load_pilot_flights_into_hub(pilot_name)

    def on_hub_flight_selected(self, flight_number: int):
        flights = self.pilot_flights.get(self.current_pilot, [])
        for f in flights:
            if f.flight_number == flight_number:
                self.current_flight = f
                self.step4_widget.load_flight(f)
                self.status_label.setText(f"Caricato Volo {f.flight_number} di '{self.current_pilot}' ({len(f.clips)} clip, {len(f.chapters)} manovre).")
                break

    def load_pilot_flights_into_hub(self, pilot_name: str):
        self.current_pilot = pilot_name
        flights = self.pilot_flights.get(pilot_name, [])
        if not flights:
            self.step4_widget.set_flights_list([])
            return

        self.step4_widget.set_flights_list(flights, current_flight_number=flights[0].flight_number)
        self.current_flight = flights[0]
        self.step4_widget.load_flight(flights[0])
        self.status_label.setText(f"Caricato Volo {flights[0].flight_number} di '{pilot_name}'.")

    def save_flight_changes(self):
        if not self.current_flight:
            return

        # Sincronizza i capitoli dalla tabella
        table = self.step4_widget.table_chapters
        for row in range(table.rowCount()):
            name_item = table.item(row, 1)
            if name_item and row < len(self.current_flight.chapters):
                self.current_flight.chapters[row].maneuver_name = name_item.text().strip()

        out_dir = self.txt_output_dir.text().strip() or "output_siv"
        pilot_dir = os.path.join(out_dir, self.current_pilot)
        flight_dir = os.path.join(pilot_dir, self.current_flight.flight_id)
        self.current_flight.save_to_folder(flight_dir)

        QMessageBox.information(self, "Salvataggio Completato", f"Modifiche salvate con successo in:\n{flight_dir}")

    def open_existing_replay_folder(self):
        """Apre un output o memory stick esistente ed entra subito in modalità Pure Replay."""
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella corso SIV esistente (su PC o Chiavetta USB)")
        if not d:
            return

        manifest = SivCourseManifest.load(d)
        if manifest:
            self.pilots_info = manifest.piloti

        # Cerca tutti i voli salvati
        self.pilot_flights = {}
        for entry in os.scandir(d):
            if entry.is_dir():
                pilot_name = entry.name
                flights = []
                for sub in os.scandir(entry.path):
                    if sub.is_dir() and sub.name.startswith("Volo_"):
                        f = SIVFlight.load_from_folder(sub.path)
                        if f:
                            flights.append(f)
                if flights:
                    flights.sort(key=lambda x: x.flight_number)
                    self.pilot_flights[pilot_name] = flights

        if not self.pilot_flights:
            QMessageBox.warning(self, "Nessun Volo Trovato", "Nessun dato di volo trovato nella cartella selezionata.")
            return

        self.txt_output_dir.setText(d)
        pilots_with_flights = list(self.pilot_flights.keys())

        p_info_map = {p.nome: p for p in self.pilots_info}
        display_pilots = []
        for p_name in pilots_with_flights:
            if p_name in p_info_map:
                p = p_info_map[p_name]
                desc = f"{p.nome}"
                if p.vela_marca_modello:
                    desc += f" [{p.vela_marca_modello}"
                    if p.colori_vela:
                        desc += f" - {p.colori_vela}"
                    desc += "]"
                display_pilots.append((p_name, desc))
            else:
                display_pilots.append((p_name, p_name))

        first_pilot = pilots_with_flights[0]
        self.step4_widget.set_pilots_list(display_pilots, current_pilot=first_pilot)
        self.go_to_step(3)
        self.load_pilot_flights_into_hub(first_pilot)
        self.status_label.setText(f"Sessione caricata in Pure Replay da: {d}")

    def on_error(self, err_msg):
        self.progress_bar.setVisible(False)
        self.btn_detect_pilots.setEnabled(True)
        self.log(f"<font color='red'><b>ERRORE:</b> {err_msg}</font>")
        QMessageBox.critical(self, "Errore", err_msg)
