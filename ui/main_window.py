import os
import glob
import time
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QMessageBox, QProgressBar,
    QStackedWidget, QTextEdit, QGroupBox, QFrame, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings

from core.audio_extractor import extract_audio
from core.transcriber import SIVTranscriber
from core.pilot_detector import PilotDetector, VideoPilotMatch
from core.file_sorter import FileSorter
from core.video_concatenator import VideoConcatenator
from core.maneuver_detector import ManeuverDetector
from core.timeline_merger import VideoTranscriptionCache, merge_transcriptions_with_offset
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
        self.setWindowTitle("SIV Video Analyzer & Manager - Procedura Guidata")
        self.resize(1150, 780)

        self.transcriber = SIVTranscriber(model_size="small")
        self.maneuver_detector = ManeuverDetector()
        self.detected_matches = []
        self.sorted_folders = {}
        self.concatenated_videos = {}
        self.current_pilot_video = None
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
        self.lbl_step2 = QLabel("2. Revisione & Smistamento Video")
        self.lbl_step3 = QLabel("3. Video Montati & Manovre SIV")

        h_layout.addWidget(self.lbl_step1)
        h_layout.addWidget(QLabel(" ➔ "))
        h_layout.addWidget(self.lbl_step2)
        h_layout.addWidget(QLabel(" ➔ "))
        h_layout.addWidget(self.lbl_step3)
        h_layout.addStretch()

        main_layout.addWidget(self.header_frame)

        # Stacked Widget per le 3 pagine del Wizard
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # Step 1: Configurazione & Analisi
        self.step1_widget = QWidget()
        self.init_step1_widget()
        self.stacked_widget.addWidget(self.step1_widget)

        # Step 2: Tabella Revisione a Schermo Intero
        self.step2_widget = Step2ReviewView()
        self.step2_widget.confirmed_signal.connect(self.start_sorting_and_concatenation)
        self.step2_widget.back_signal.connect(lambda: self.go_to_step(0))
        self.stacked_widget.addWidget(self.step2_widget)

        # Step 3: Hub Montato & Player Capitoli
        self.step3_widget = ChaptersView()
        self.step3_widget.pilot_selected_signal.connect(self.on_hub_pilot_selected)
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

        # Imposta lo step iniziale
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
        layout.setSpacing(12)

        # Selezione Cartella
        box_input = QGroupBox("Cartella Video Sorgente")
        l_in = QHBoxLayout(box_input)
        self.txt_source_dir = QLineEdit()
        self.txt_source_dir.setPlaceholderText("Seleziona la cartella contenente i video del corso SIV...")
        l_in.addWidget(self.txt_source_dir)
        btn_browse_src = QPushButton("Sfoglia...")
        btn_browse_src.clicked.connect(self.browse_source_dir)
        l_in.addWidget(btn_browse_src)
        layout.addWidget(box_input)

        # Lista Piloti del Corso (Opzionale ma consigliata)
        box_pilots = QGroupBox("Lista Nomi Piloti del Corso (consigliata per matching radio perfetto)")
        l_pilots = QVBoxLayout(box_pilots)
        self.txt_pilots = QLineEdit()
        self.txt_pilots.setPlaceholderText("Es: Marco Rossi, Luca Bianchi, Andrea, Sara...")
        l_pilots.addWidget(self.txt_pilots)
        layout.addWidget(box_pilots)

        # Cartella di Output e Modalità Modello Whisper
        row_config = QHBoxLayout()

        box_output = QGroupBox("Cartella di Destinazione (Output)")
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

    def clear_cache(self):
        """Elimina i file di cache JSON e WAV dalla cartella temp."""
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

        saved_pilots = self.settings.value("pilots", "")
        if saved_pilots:
            self.txt_pilots.setText(saved_pilots)

        saved_out = self.settings.value("output_dir", "")
        if saved_out:
            self.txt_output_dir.setText(saved_out)

        saved_model = self.settings.value("whisper_model", "base")
        idx = self.combo_model.findData(saved_model)
        if idx >= 0:
            self.combo_model.setCurrentIndex(idx)
        self.transcriber.set_model_size(saved_model)

        # Collega i segnali di salvataggio automatico solo ORA che i campi sono stati popolati
        self.txt_source_dir.textChanged.connect(self.save_settings)
        self.txt_pilots.textChanged.connect(self.save_settings)
        self.txt_output_dir.textChanged.connect(self.save_settings)
        self.combo_model.currentIndexChanged.connect(self.on_model_changed)

    def save_settings(self):
        self.settings.setValue("source_dir", self.txt_source_dir.text().strip())
        self.settings.setValue("pilots", self.txt_pilots.text().strip())
        self.settings.setValue("output_dir", self.txt_output_dir.text().strip())
        self.settings.setValue("whisper_model", self.combo_model.currentData() or "base")
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

        pilots_raw = self.txt_pilots.text().split(",")
        pilots = [p.strip() for p in pilots_raw if p.strip()]

        # Supporto esteso formati video inclusi i formati Sony AVCHD (.MTS, .M2TS) e XAVC (.MXF, .MP4)
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

        # Rimuovi duplicati e ordina
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
            detector = PilotDetector(pilots_list=pilots, transcriber=self.transcriber)
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

            total_elapsed = int(time.time() - start_wall_time)
            progress_sig.emit(f"Riconoscimento piloti completato in {total_elapsed // 60:02d}m {total_elapsed % 60:02d}s!", 100)
            return matches

        self.worker = WorkerThread(task)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.finished_signal.connect(self.on_pilots_detected)
        self.worker.cancelled_signal.connect(self.on_task_cancelled)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def cancel_current_task(self):
        """Richiede l'interruzione del task in background."""
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

        pilots_raw = self.txt_pilots.text().split(",")
        pilots = [p.strip() for p in pilots_raw if p.strip()]

        # Passa allo Step 2 (Schermata Revisione)
        self.step2_widget.set_data(matches, pilots_list=pilots)
        self.go_to_step(1)
        self.status_label.setText("Verifica l'assegnazione dei video ai piloti e clicca 'Conferma e Crea Video Montati'.")

    def start_sorting_and_concatenation(self):
        """Esegue smistamento fisico e montaggio per pilota."""
        out_dir = self.txt_output_dir.text().strip() or "output_siv"
        sorter = FileSorter(base_output_dir=out_dir)
        self.sorted_folders = sorter.sort_videos(self.detected_matches, move=False)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_cancel_task.setVisible(True)

        def task(progress_sig, is_cancelled):
            concatenator = VideoConcatenator()
            concatenated_videos = {}
            total = len(self.sorted_folders)
            start_wall_time = time.time()

            for i, (pilot, files) in enumerate(self.sorted_folders.items()):
                if is_cancelled():
                    progress_sig.emit("Concatenazione interrotta dall'utente.", 0)
                    return concatenated_videos

                pct = int((i / total) * 100)
                elapsed = time.time() - start_wall_time
                if i > 0:
                    est_total = (elapsed / i) * total
                    rem = max(0.0, est_total - elapsed)
                    m_rem = int(rem // 60)
                    s_rem = int(rem % 60)
                    eta_str = f" | Tempo residuo stimato: {m_rem:02d}m {s_rem:02d}s"
                else:
                    eta_str = " | Calcolo tempo residuo..."

                progress_sig.emit(f"Concatenazione pilota {i+1}/{total} ({pilot}){eta_str}", pct)
                sorted_files = sorted(files, key=lambda f: os.path.getmtime(f))
                pilot_folder = os.path.join(out_dir, pilot)
                montati_folder = os.path.join(pilot_folder, "montati")
                os.makedirs(montati_folder, exist_ok=True)
                merged_output = os.path.join(montati_folder, f"{pilot}_Corso_SIV_Montato.mp4")
                concatenator.concatenate_videos(sorted_files, merged_output)
                concatenated_videos[pilot] = merged_output

            total_elapsed = int(time.time() - start_wall_time)
            progress_sig.emit(f"Concatenazione completata in {total_elapsed // 60:02d}m {total_elapsed % 60:02d}s!", 100)
            return concatenated_videos

        self.worker = WorkerThread(task)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.finished_signal.connect(self.on_concatenation_done)
        self.worker.cancelled_signal.connect(self.on_task_cancelled)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def on_concatenation_done(self, concatenated_videos):
        self.progress_bar.setVisible(False)
        self.btn_cancel_task.setVisible(False)
        self.concatenated_videos = concatenated_videos

        pilots_with_video = list(concatenated_videos.keys())
        if not pilots_with_video:
            QMessageBox.warning(self, "Attenzione", "Nessun video montato generato.")
            return

        # Configura lo Step 3 con la lista dei piloti
        first_pilot = pilots_with_video[0]
        self.step3_widget.set_pilots_list(pilots_with_video, current_pilot=first_pilot)
        self.go_to_step(2)
        self.load_pilot_into_hub(first_pilot)

    def on_hub_pilot_selected(self, pilot_name: str):
        self.load_pilot_into_hub(pilot_name)

    def load_pilot_into_hub(self, pilot_name: str):
        vpath = self.concatenated_videos.get(pilot_name)
        if not vpath or not os.path.exists(vpath):
            return

        self.current_pilot_video = vpath
        self.step3_widget.load_video(vpath)

        # Ricomponi istantaneamente i capitoli tramite cache
        pilot_matches_map = {m.filename: m for m in self.detected_matches}
        matched_caches = []
        if pilot_name in self.sorted_folders:
            sorted_files = sorted(self.sorted_folders[pilot_name], key=lambda f: os.path.getmtime(f))
            for sf in sorted_files:
                fname = os.path.basename(sf)
                if fname in pilot_matches_map and pilot_matches_map[fname].segments:
                    m = pilot_matches_map[fname]
                    c = VideoTranscriptionCache(
                        video_path=sf,
                        filename=fname,
                        duration=m.duration,
                        segments=m.segments
                    )
                    matched_caches.append(c)

        if matched_caches:
            segments = merge_transcriptions_with_offset(matched_caches)
            chapters = self.maneuver_detector.detect_chapters(segments)
            self.step3_widget.set_chapters(chapters)
            self.status_label.setText(f"Video montato di '{pilot_name}' caricato: {len(chapters)} capitoli / manovre pronte.")
        else:
            self.step3_widget.set_chapters([])
            self.status_label.setText(f"Video montato di '{pilot_name}' caricato.")

    def on_error(self, err_msg):
        self.progress_bar.setVisible(False)
        self.btn_detect_pilots.setEnabled(True)
        self.log(f"<font color='red'><b>ERRORE:</b> {err_msg}</font>")
        QMessageBox.critical(self, "Errore", err_msg)
