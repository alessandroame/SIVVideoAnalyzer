import os
import glob
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QMessageBox, QProgressBar,
    QTabWidget, QTextEdit, QListWidget, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.audio_extractor import extract_audio
from core.transcriber import SIVTranscriber
from core.pilot_detector import PilotDetector, VideoPilotMatch
from core.file_sorter import FileSorter
from core.video_concatenator import VideoConcatenator
from core.maneuver_detector import ManeuverDetector
from core.timeline_merger import VideoTranscriptionCache, merge_transcriptions_with_offset
from ui.step1_sort_dialog import SorterApprovalDialog
from ui.step3_chapters_view import ChaptersView

class WorkerThread(QThread):
    progress_signal = pyqtSignal(str, int)
    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)

    def __init__(self, task_fn, *args, **kwargs):
        super().__init__()
        self.task_fn = task_fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            res = self.task_fn(self.progress_signal, *self.args, **self.kwargs)
            self.finished_signal.emit(res)
        except Exception as e:
            import traceback
            self.error_signal.emit(f"{str(e)}\n\n{traceback.format_exc()}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SIV Video Analyzer & Manager")
        self.resize(1100, 750)

        self.transcriber = SIVTranscriber(model_size="small")
        self.maneuver_detector = ManeuverDetector()
        self.detected_matches = []
        self.sorted_folders = {}
        self.current_pilot_video = None

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tab Widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Scheda 1: Smistamento & Montaggio
        self.tab_workflow = QWidget()
        self.init_workflow_tab()
        self.tabs.addTab(self.tab_workflow, "1. Riconoscimento Piloti & Montaggio")

        # Scheda 2: Capitoli & Player
        self.chapters_view = ChaptersView()
        self.tabs.addTab(self.chapters_view, "2. Analisi Manovre & Player Video")

        # Barra di avanzamento e stato globale
        self.status_box = QHBoxLayout()
        self.status_label = QLabel("Pronto.")
        self.status_box.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.status_box.addWidget(self.progress_bar)

        main_layout.addLayout(self.status_box)

    def init_workflow_tab(self):
        layout = QVBoxLayout(self.tab_workflow)

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

        # Cartella di Output
        box_output = QGroupBox("Cartella di Destinazione (Output)")
        l_out = QHBoxLayout(box_output)
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setText(os.path.abspath("output_siv"))
        l_out.addWidget(self.txt_output_dir)
        btn_browse_out = QPushButton("Sfoglia...")
        btn_browse_out.clicked.connect(self.browse_output_dir)
        l_out.addWidget(btn_browse_out)
        layout.addWidget(box_output)

        # Log eventi
        layout.addWidget(QLabel("<b>Log Operazioni:</b>"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        # Pulsanti di Azione
        btn_layout = QHBoxLayout()
        self.btn_detect_pilots = QPushButton("Avvia Analisi & Smistamento Piloti")
        self.btn_detect_pilots.setStyleSheet("background-color: #0288d1; color: white; font-weight: bold; padding: 8px;")
        self.btn_detect_pilots.clicked.connect(self.start_pilot_detection)
        btn_layout.addWidget(self.btn_detect_pilots)

        self.btn_concat_all = QPushButton("Concatena Video per Pilota")
        self.btn_concat_all.setEnabled(False)
        self.btn_concat_all.setStyleSheet("background-color: #388e3c; color: white; font-weight: bold; padding: 8px;")
        self.btn_concat_all.clicked.connect(self.start_concatenation)
        btn_layout.addWidget(self.btn_concat_all)

        self.btn_analyze_chapters = QPushButton("Analizza Manovre Video Montato")
        self.btn_analyze_chapters.setEnabled(False)
        self.btn_analyze_chapters.setStyleSheet("background-color: #7b1fa2; color: white; font-weight: bold; padding: 8px;")
        self.btn_analyze_chapters.clicked.connect(self.start_chapter_analysis)
        btn_layout.addWidget(self.btn_analyze_chapters)

        layout.addLayout(btn_layout)

    def log(self, msg: str):
        self.log_text.append(msg)

    def browse_source_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella video sorgente")
        if d:
            self.txt_source_dir.setText(d)

    def browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella di destinazione")
        if d:
            self.txt_output_dir.setText(d)

    def start_pilot_detection(self):
        src = self.txt_source_dir.text().strip()
        if not src or not os.path.exists(src):
            QMessageBox.warning(self, "Attenzione", "Seleziona una cartella sorgente valida.")
            return

        pilots_raw = self.txt_pilots.text().split(",")
        pilots = [p.strip() for p in pilots_raw if p.strip()]

        exts = ["*.mp4", "*.mov", "*.avi", "*.mkv", "*.MP4", "*.MOV"]
        video_files = []
        for ext in exts:
            video_files.extend(glob.glob(os.path.join(src, ext)))
        video_files = list(set(video_files))

        if not video_files:
            QMessageBox.warning(self, "Nessun video", "Nessun file video trovato nella cartella specificata.")
            return

        self.log(f"Trovati {len(video_files)} video da analizzare...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_detect_pilots.setEnabled(False)

        def task(progress_sig):
            detector = PilotDetector(pilots_list=pilots, transcriber=self.transcriber)
            matches = []
            total = len(video_files)
            for i, vf in enumerate(video_files):
                progress_sig.emit(f"Analisi audio per pilota: {os.path.basename(vf)}...", int((i / total) * 100))
                m = detector.identify_pilot_from_audio(vf)
                matches.append(m)
            progress_sig.emit("Riconoscimento piloti completato!", 100)
            return matches

        self.worker = WorkerThread(task)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.finished_signal.connect(self.on_pilots_detected)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def on_progress(self, msg, val):
        self.status_label.setText(msg)
        self.progress_bar.setValue(val)
        self.log(msg)

    def on_pilots_detected(self, matches):
        self.progress_bar.setVisible(False)
        self.btn_detect_pilots.setEnabled(True)
        self.detected_matches = matches

        # Mostra dialog di revisione e approvazione
        pilots_raw = self.txt_pilots.text().split(",")
        pilots = [p.strip() for p in pilots_raw if p.strip()]

        dialog = SorterApprovalDialog(matches, pilots_list=pilots, parent=self)
        if dialog.exec() and dialog.confirmed:
            # Esegui lo smistamento fisico
            out_dir = self.txt_output_dir.text().strip() or "output_siv"
            sorter = FileSorter(base_output_dir=out_dir)
            self.sorted_folders = sorter.sort_videos(matches, move=False)
            self.log("<b>Smistamento completato con successo!</b>")
            for pilot, files in self.sorted_folders.items():
                self.log(f" - Pilota '{pilot}': {len(files)} video")
            self.btn_concat_all.setEnabled(True)

    def start_concatenation(self):
        if not self.sorted_folders:
            QMessageBox.warning(self, "Attenzione", "Nessuna cartella pilota disponibile per il montaggio.")
            return

        out_dir = self.txt_output_dir.text().strip() or "output_siv"
        self.btn_concat_all.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        def task(progress_sig):
            concatenator = VideoConcatenator()
            concatenated_videos = {}
            total = len(self.sorted_folders)
            for i, (pilot, files) in enumerate(self.sorted_folders.items()):
                progress_sig.emit(f"Concatenazione video per pilota: {pilot}...", int((i / total) * 100))
                # Ordina i file cronologicamente
                sorted_files = sorted(files, key=lambda f: os.path.getmtime(f))
                # Salva il video montato in una sottocartella dedicata 'montati'
                pilot_folder = os.path.join(out_dir, pilot)
                montati_folder = os.path.join(pilot_folder, "montati")
                os.makedirs(montati_folder, exist_ok=True)
                merged_output = os.path.join(montati_folder, f"{pilot}_Corso_SIV_Montato.mp4")
                concatenator.concatenate_videos(sorted_files, merged_output)
                concatenated_videos[pilot] = merged_output
            progress_sig.emit("Concatenazione completata per tutti i piloti!", 100)
            return concatenated_videos

        self.worker = WorkerThread(task)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.finished_signal.connect(self.on_concatenation_done)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def on_concatenation_done(self, concatenated_videos):
        self.progress_bar.setVisible(False)
        self.btn_concat_all.setEnabled(True)
        self.concatenated_videos = concatenated_videos
        self.log("<b>Tutti i video dei piloti sono stati montati e concatenati!</b>")
        for pilot, vpath in concatenated_videos.items():
            self.log(f" - {pilot}: {vpath}")
            self.current_pilot_video = vpath  # Imposta l'ultimo o il primo disponibile

        self.btn_analyze_chapters.setEnabled(True)

    def start_chapter_analysis(self):
        if not self.current_pilot_video or not os.path.exists(self.current_pilot_video):
            vpath, _ = QFileDialog.getOpenFileName(self, "Seleziona video montato da analizzare", "", "Video (*.mp4 *.mov *.avi)")
            if not vpath:
                return
            self.current_pilot_video = vpath

        vpath = self.current_pilot_video
        self.btn_analyze_chapters.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # 1. Verifica se possiamo ricomporre la trascrizione istantaneamente dalla cache (One-Pass)
        pilot_matches_map = {m.filename: m for m in self.detected_matches}

        def task(progress_sig):
            # Cerca i file originali che compongono questo pilota
            matched_caches = []
            if hasattr(self, 'sorted_folders'):
                for pilot, files in self.sorted_folders.items():
                    if f"{pilot}_Corso_SIV_Montato" in os.path.basename(vpath):
                        sorted_files = sorted(files, key=lambda f: os.path.getmtime(f))
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
                        break

            if matched_caches:
                progress_sig.emit("Ricomposizione istantanea trascrizione con offset temporali...", 50)
                segments = merge_transcriptions_with_offset(matched_caches)
                progress_sig.emit("Riconoscimento manovre SIV (istantaneo da cache)...", 85)
                chapters = self.maneuver_detector.detect_chapters(segments)
                progress_sig.emit("Capitoli generati istantaneamente!", 100)
                return chapters

            # Fallback nel caso di caricamento video manuale non presente in cache
            progress_sig.emit("Estrazione traccia audio completa...", 10)
            wav_path = os.path.join("temp", "merged_analysis.wav")
            extract_audio(vpath, wav_path)

            progress_sig.emit("Trascrizione audio con Whisper in corso...", 30)
            segments = self.transcriber.transcribe(wav_path, language="it")

            progress_sig.emit("Riconoscimento comandi e manovre SIV...", 80)
            chapters = self.maneuver_detector.detect_chapters(segments)

            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

            progress_sig.emit("Analisi manovre completata!", 100)
            return chapters

        self.worker = WorkerThread(task)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.finished_signal.connect(self.on_chapters_analyzed)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    def on_chapters_analyzed(self, chapters):
        self.progress_bar.setVisible(False)
        self.btn_analyze_chapters.setEnabled(True)
        self.log(f"<b>Rilevati {len(chapters)} capitoli / manovre SIV!</b>")

        # Passa alla scheda 2 del Player
        self.chapters_view.load_video(self.current_pilot_video)
        self.chapters_view.set_chapters(chapters)
        self.tabs.setCurrentIndex(1)
        QMessageBox.information(self, "Analisi Completata", f"Trovate {len(chapters)} manovre!\nPuoi navigare tra i capitoli nel player.")

    def on_error(self, err_msg):
        self.progress_bar.setVisible(False)
        self.btn_detect_pilots.setEnabled(True)
        self.btn_concat_all.setEnabled(True)
        self.btn_analyze_chapters.setEnabled(True)
        self.log(f"<font color='red'><b>ERRORE:</b> {err_msg}</font>")
        QMessageBox.critical(self, "Errore", err_msg)
