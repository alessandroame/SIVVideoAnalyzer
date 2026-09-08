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
            res = self.task_fn(self.progress_signal, self.is_cancelled, *self.args, **self.kwargs)
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

        # Wizard Step Header / Stepper indicator
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

        self.lbl_step1 = QLabel("1. Configurazione & Riconoscimento")
        self.lbl_step2 = QLabel("2. Revisione & Assegnazione per Volo")
        self.lbl_step3 = QLabel("3. Debriefing Didattico & Player Voli")

        h_layout.addWidget(self.lbl_step1)
        h_layout.addWidget(QLabel(" ➔ "))
        h_layout.addWidget(self.lbl_step2)
        h_layout.addWidget(QLabel(" ➔ "))
        h_layout.addWidget(self.lbl_step3)
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

        # Stacked Widget per le 3 pagine del Wizard
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # Step 1: Configurazione & Analisi
        self.step1_widget = QWidget()
        self.init_step1_widget()
        self.stacked_widget.addWidget(self.step1_widget)

        # Step 2: Tabella Revisione a Schermo Intero (con Voli)
        self.step2_widget = Step2ReviewView()
        self.step2_widget.confirmed_signal.connect(self.on_review_confirmed_enter_debriefing)
        self.step2_widget.back_signal.connect(lambda: self.go_to_step(0))
        self.stacked_widget.addWidget(self.step2_widget)

        # Step 3: Hub Debriefing & Player Voli
        self.step3_widget = ChaptersView()
        self.step3_widget.pilot_selected_signal.connect(self.on_hub_pilot_selected)
        self.step3_widget.flight_selected_signal.connect(self.on_hub_flight_selected)
        self.step3_widget.save_changes_signal.connect(self.save_flight_changes)
        self.step3_widget.back_signal.connect(lambda: self.go_to_step(1))
        self.stacked_widget.addWidget(self.step3_widget)

        # Barra di avanzamento e stato globale con pulsante di interruzione (in basso)
        self.status_box = QHBoxLayout()
        self.status_label = QLabel("Pronto.")
        self.status_label.setStyleSheet("font-weight: 500;")
        self.status_box.addWidget(self.status_label, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #bbb;
                border-radius: 4px;
                text-align: center;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #0288d1;
            }
        """)
        self.status_box.addWidget(self.progress_bar, stretch=2)

        self.btn_cancel_task = QPushButton("⏹ Interrompi")
        self.btn_cancel_task.setVisible(False)
        self.btn_cancel_task.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; 
                color: white; 
                font-weight: bold; 
                padding: 4px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
        """)
        self.btn_cancel_task.clicked.connect(self.cancel_current_task)
        self.status_box.addWidget(self.btn_cancel_task)

        main_layout.addLayout(self.status_box)

        self.go_to_step(0)

    def update_stepper_style(self, current_step: int):
        active_style = "color: #38bdf8; font-weight: bold; text-decoration: underline;"
        inactive_style = "color: #94a3b8; font-weight: normal;"

        self.lbl_step1.setStyleSheet(active_style if current_step == 0 else inactive_style)
        self.lbl_step2.setStyleSheet(active_style if current_step == 1 else inactive_style)
        self.lbl_step3.setStyleSheet(active_style if current_step == 2 else inactive_style)

    def go_to_step(self, step_idx: int):
        self.stacked_widget.setCurrentIndex(step_idx)
        self.update_stepper_style(step_idx)

    def init_step1_widget(self):
        layout = QVBoxLayout(self.step1_widget)
        layout.setSpacing(10)

        # Selezione Cartella Sorgente Video
        box_input = QGroupBox("Cartella Video Sorgente (supporta schede SD Sony .MTS/.MXF/MP4)")
        l_in = QHBoxLayout(box_input)
        self.txt_source_dir = QLineEdit()
        self.txt_source_dir.setPlaceholderText("Seleziona la cartella contenente i video del corso SIV...")
        l_in.addWidget(self.txt_source_dir)
        btn_browse_src = QPushButton("Sfoglia...")
        btn_browse_src.clicked.connect(self.browse_source_dir)
        l_in.addWidget(btn_browse_src)
        layout.addWidget(box_input)

        # Gestione Piloti del Corso con Modello Vela e Colori
        box_pilots = QGroupBox("Anagrafica Piloti del Corso (Vela e Colori per identificazione e memoria chiavetta)")
        l_pilots = QVBoxLayout(box_pilots)

        self.table_pilots = QTableWidget(0, 3)
        self.table_pilots.setHorizontalHeaderLabels(["Nome e Cognome Pilota", "Modello Vela (es. Rush 6)", "Colori Vela (es. Rosso/Nero)"])
        self.table_pilots.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_pilots.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_pilots.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_pilots.setMaximumHeight(130)
        l_pilots.addWidget(self.table_pilots)

        pilot_btn_layout = QHBoxLayout()
        btn_add_p = QPushButton("+ Aggiungi Pilota")
        btn_add_p.clicked.connect(self.add_pilot_row)
        pilot_btn_layout.addWidget(btn_add_p)

        btn_del_p = QPushButton("- Rimuovi Selezionato")
        btn_del_p.clicked.connect(self.remove_pilot_row)
        pilot_btn_layout.addWidget(btn_del_p)
        pilot_btn_layout.addStretch()

        l_pilots.addLayout(pilot_btn_layout)
        layout.addWidget(box_pilots)

        # Cartella di Output e Modalità Modello Whisper
        row_config = QHBoxLayout()

        box_output = QGroupBox("Cartella di Destinazione (Output Portatile / Chiavetta USB)")
        l_out = QHBoxLayout(box_output)
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setText(os.path.abspath("output_siv"))
        l_out.addWidget(self.txt_output_dir)
        btn_browse_out = QPushButton("Sfoglia...")
        btn_browse_out.clicked.connect(self.browse_output_dir)
        l_out.addWidget(btn_browse_out)
        row_config.addWidget(box_output, stretch=3)

        box_model = QGroupBox("Modello Whisper (Velocità / Precisione)")
        l_model = QHBoxLayout(box_model)
        self.combo_model = QComboBox()
        self.combo_model.addItem("Ultra Veloce (Base - Consigliato)", "base")
        self.combo_model.addItem("Alta Precisione (Small)", "small")
        l_model.addWidget(self.combo_model)
        row_config.addWidget(box_model, stretch=2)

        layout.addLayout(row_config)

        # Log eventi
        layout.addWidget(QLabel("<b>Log Operazioni:</b>"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        layout.addWidget(self.log_text)

        # Pulsante di Azione Primario e Gestione Cache
        btn_action_layout = QHBoxLayout()

        self.btn_clear_cache = QPushButton("🗑 Svuota Cache Audio")
        self.btn_clear_cache.setToolTip("Elimina le trascrizioni memorizzate per rieseguire l'analisi audio da zero con Whisper")
        self.btn_clear_cache.setStyleSheet("""
            QPushButton {
                background-color: #475569; 
                color: #f1f5f9; 
                font-size: 13px; 
                padding: 12px 16px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #64748b;
            }
        """)
        self.btn_clear_cache.clicked.connect(self.clear_cache)
        btn_action_layout.addWidget(self.btn_clear_cache)

        self.btn_detect_pilots = QPushButton("Avvia Analisi Audio & Riconoscimento Piloti ➡")
        self.btn_detect_pilots.setStyleSheet("""
            QPushButton {
                background-color: #0288d1; 
                color: white; 
                font-weight: bold; 
                font-size: 14px; 
                padding: 12px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0277bd;
            }
        """)
        self.btn_detect_pilots.clicked.connect(self.start_pilot_detection)
        btn_action_layout.addWidget(self.btn_detect_pilots, stretch=1)

        layout.addLayout(btn_action_layout)

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

        self.log(f"Trovati {len(video_files)} video da analizzare...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_cancel_task.setVisible(True)
        self.btn_detect_pilots.setEnabled(False)

        def task(progress_sig, is_cancelled):
            detector = PilotDetector(pilots_list=pilot_names, transcriber=self.transcriber)
            matches = []
            total = len(video_files)
            start_wall_time = time.time()
            last_eta_str = "Stima in corso..."

            for i, vf in enumerate(video_files):
                if is_cancelled():
                    progress_sig.emit("Operazione interrotta dall'utente.", 0)
                    return matches

                fname = os.path.basename(vf)
                base_percent = (i / total) * 100.0
                file_slice = 100.0 / total

                progress_sig.emit(
                    f"Video {i+1}/{total} ({fname}): estrazione e trascrizione audio... | {last_eta_str}",
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
                        last_eta_str = f"Tempo residuo totale stimato: {m_rem:02d}m {s_rem:02d}s" if remaining > 2 else "Completamento in corso..."

                    m_curr = int(curr_sec // 60)
                    s_curr = int(curr_sec % 60)
                    m_tot = int(dur_sec // 60)
                    s_tot = int(dur_sec % 60)

                    progress_sig.emit(
                        f"Video {i+1}/{total} ({fname}) | Audio: {m_curr:02d}:{s_curr:02d}/{m_tot:02d}:{s_tot:02d} | {last_eta_str}",
                        int(overall_pct)
                    )

                m = detector.identify_pilot_from_audio(
                    vf, 
                    progress_callback=on_file_progress,
                    is_cancelled_callback=is_cancelled
                )
                if is_cancelled():
                    return matches
                matches.append(m)

            # Raggruppa provvisoriamente per numero di volo per ciascun pilota
            pilot_map = {}
            for m in matches:
                pilot_map.setdefault(m.detected_pilot, []).append(m)

            grouper = FlightGrouper()
            for p, p_matches in pilot_map.items():
                p_flights = grouper.group_pilot_matches_into_flights(p, p_matches)
                for f in p_flights:
                    clip_fnames = {c.filename for c in f.clips}
                    for m in p_matches:
                        if m.filename in clip_fnames:
                            m.flight_number = f.flight_number

            total_elapsed = int(time.time() - start_wall_time)
            progress_sig.emit(f"Riconoscimento completato in {total_elapsed // 60:02d}m {total_elapsed % 60:02d}s!", 100)
            return matches

        self.worker = WorkerThread(task)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.finished_signal.connect(self.on_pilots_detected)
        self.worker.cancelled_signal.connect(self.on_task_cancelled)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def cancel_current_task(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.status_label.setText("Interruzione in corso...")
            self.btn_cancel_task.setEnabled(False)
            self.worker.request_cancel()

    def on_task_cancelled(self):
        self.progress_bar.setVisible(False)
        self.btn_cancel_task.setVisible(False)
        self.btn_cancel_task.setEnabled(True)
        self.btn_detect_pilots.setEnabled(True)
        self.status_label.setText("Elaborazione interrotta dall'utente.")
        self.log("<b>Elaborazione interrotta dall'utente.</b>")

    def on_progress(self, msg, val):
        self.status_label.setText(msg)
        self.progress_bar.setValue(val)

    def on_pilots_detected(self, matches):
        self.progress_bar.setVisible(False)
        self.btn_cancel_task.setVisible(False)
        self.btn_detect_pilots.setEnabled(True)
        self.detected_matches = matches

        pilot_names = [p.nome for p in self.pilots_info]

        # Passa allo Step 2 (Schermata Revisione con Voli)
        self.step2_widget.set_data(matches, pilots_list=pilot_names)
        self.go_to_step(1)
        self.status_label.setText("Verifica piloti e numeri di volo, poi clicca 'Conferma ed Entra nel Debriefing'.")

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
        self.step3_widget.set_pilots_list(display_pilots, current_pilot=first_pilot)
        self.go_to_step(2)
        self.load_pilot_flights_into_hub(first_pilot)

    def on_hub_pilot_selected(self, pilot_name: str):
        self.load_pilot_flights_into_hub(pilot_name)

    def on_hub_flight_selected(self, flight_number: int):
        flights = self.pilot_flights.get(self.current_pilot, [])
        for f in flights:
            if f.flight_number == flight_number:
                self.current_flight = f
                self.step3_widget.load_flight(f)
                self.status_label.setText(f"Caricato Volo {f.flight_number} di '{self.current_pilot}' ({len(f.clips)} clip, {len(f.chapters)} manovre).")
                break

    def load_pilot_flights_into_hub(self, pilot_name: str):
        self.current_pilot = pilot_name
        flights = self.pilot_flights.get(pilot_name, [])
        if not flights:
            self.step3_widget.set_flights_list([])
            return

        self.step3_widget.set_flights_list(flights, current_flight_number=flights[0].flight_number)
        self.current_flight = flights[0]
        self.step3_widget.load_flight(flights[0])
        self.status_label.setText(f"Caricato Volo {flights[0].flight_number} di '{pilot_name}'.")

    def save_flight_changes(self):
        if not self.current_flight:
            return

        # Sincronizza i capitoli dalla tabella
        table = self.step3_widget.table_chapters
        for row in range(table.rowCount()):
            name_item = table.item(row, 2)
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
        self.step3_widget.set_pilots_list(display_pilots, current_pilot=first_pilot)
        self.go_to_step(2)
        self.load_pilot_flights_into_hub(first_pilot)
        self.status_label.setText(f"Sessione caricata in Pure Replay da: {d}")

    def on_error(self, err_msg):
        self.progress_bar.setVisible(False)
        self.btn_detect_pilots.setEnabled(True)
        self.log(f"<font color='red'><b>ERRORE:</b> {err_msg}</font>")
        QMessageBox.critical(self, "Errore", err_msg)
