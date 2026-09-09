import sys
import os
import time
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QSlider,
    QFrame, QMessageBox, QSplitter, QProgressBar, QComboBox, QSpinBox
)
from PyQt6.QtCore import Qt, QUrl, QTime, QSettings, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut, QColor, QBrush, QFont
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from core.sidecar_manager import SidecarData
from core.audio_extractor import get_video_creation_time, get_formatted_video_datetime
from core.pilot_detector import PilotDetector, VideoPilotMatch, VideoTranscriptionCache
from core.transcriber import SIVTranscriber
from core.maneuver_detector import ManeuverDetector
from core.flight_grouper import VideoExporter
from ui.maneuvers_dialog import ManeuversConfigDialog
from ui.add_chapter_dialog import AddChapterQuickDialog

def ensure_arrow_icons() -> tuple[str, str]:
    """Genera le icone SVG ciano su disco se non esistono e restituisce i percorsi formattati per QSS."""
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    os.makedirs(icons_dir, exist_ok=True)
    up_path = os.path.abspath(os.path.join(icons_dir, "arrow_up.svg")).replace("\\", "/")
    down_path = os.path.abspath(os.path.join(icons_dir, "arrow_down.svg")).replace("\\", "/")
    
    if not os.path.exists(up_path):
        with open(up_path, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"><polygon points="12,5 21,18 3,18" fill="#38bdf8"/></svg>')
            
    if not os.path.exists(down_path):
        with open(down_path, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"><polygon points="3,6 21,6 12,19" fill="#38bdf8"/></svg>')
            
    return up_path, down_path

ARROW_UP_PATH, ARROW_DOWN_PATH = ensure_arrow_icons()

# ------------------------------------------------------------------
# WIDGET VIDEO PERSONALIZZATO (GESTIONE ESC, FULLSCREEN & KEYBOARD)
# ------------------------------------------------------------------
class SIVVideoWidget(QVideoWidget):
    """QVideoWidget con gestione integrata della tastiera in modalità a tutto schermo.
    Risolve il blocco del tasto ESC e F quando il widget viene staccato da MainWindow."""
    escape_pressed = pyqtSignal()
    toggle_fullscreen_requested = pyqtSignal()
    toggle_play_requested = pyqtSignal()
    seek_requested = pyqtSignal(int)  # ms

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.setFullScreen(False)
            self.escape_pressed.emit()
            event.accept()
        elif key == Qt.Key.Key_F:
            self.setFullScreen(not self.isFullScreen())
            self.toggle_fullscreen_requested.emit()
            event.accept()
        elif key == Qt.Key.Key_Space:
            self.toggle_play_requested.emit()
            event.accept()
        elif key == Qt.Key.Key_Left:
            self.seek_requested.emit(-5000)
            event.accept()
        elif key == Qt.Key.Key_Right:
            self.seek_requested.emit(5000)
            event.accept()
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.setFullScreen(not self.isFullScreen())
        self.toggle_fullscreen_requested.emit()
        event.accept()

# ------------------------------------------------------------------
# WORKER BACKGROUND: PRIORITÀ ASSOLUTA MANOVRE & ZERO ATTESE
# ------------------------------------------------------------------
class AnalysisWorker(QThread):
    clip_analyzed = pyqtSignal(object)              # emette VideoPilotMatch appena pronto
    clip_progress = pyqtSignal(str, float, float)   # video_path, sec_fatti, sec_totali
    overall_progress = pyqtSignal(str, int)         # eta_text, percent_globale
    status_update = pyqtSignal(str)
    maneuvers_ready = pyqtSignal(str, list)         # video_path, list of chapters

    def __init__(self, video_files, pilot_names, transcriber, priority_video=None, maneuver_detector=None):
        super().__init__()
        self.video_files = list(video_files)
        self.pilot_names = pilot_names
        self.transcriber = transcriber
        self.priority_video = priority_video
        self.maneuver_detector = maneuver_detector or ManeuverDetector()
        self._is_cancelled = False
        self._requested_priority = None

    def request_priority_video(self, video_path: str):
        """Richiesta dinamica: se l'istruttore apre un video, passa subito a calcolare le manovre di quello."""
        self._requested_priority = video_path

    def request_cancel(self):
        self._is_cancelled = True

    def _process_maneuvers_for_video(self, video_path: str, detector: PilotDetector, man_detector: ManeuverDetector):
        """Estrae e calcola immediatamente i capitoli/manovre per il video specifico."""
        try:
            sc = SidecarData(video_path)
            # Se ha già capitoli, emettili subito
            if sc.chapters:
                self.maneuvers_ready.emit(video_path, sc.chapters)
                return

            base_name = os.path.splitext(os.path.basename(video_path))[0]
            cache_file = os.path.join("temp", f"{base_name}_cache.json")
            cached = VideoTranscriptionCache.load(cache_file)
            segments = []
            if cached and cached.segments:
                segments = cached.segments
            else:
                m = detector.identify_pilot_from_audio(video_path)
                segments = getattr(m, "segments", [])

            if segments:
                detected_chaps = man_detector.detect_chapters(segments)
                ch_dicts = []
                for ch in detected_chaps:
                    ch_dicts.append({
                        "title": ch.maneuver_name,
                        "start": round(ch.start_time, 2),
                        "end": round(ch.end_time, 2),
                        "instructor_command": ch.transcription_text,
                        "notes": ch.category
                    })
                sc.chapters = ch_dicts
                sc.save()
                self.maneuvers_ready.emit(video_path, ch_dicts)
        except Exception as e:
            print(f"[Worker] Errore calcolo manovre su {video_path}: {e}")

    def run(self):
        detector = PilotDetector(pilots_list=self.pilot_names, transcriber=self.transcriber)
        man_detector = self.maneuver_detector

        # 🥇 PRIORITÀ 1: Se c'è un video prioritario specificato all'avvio, fai subito le manovre
        if self.priority_video:
            self.status_update.emit(f"⚡ Rilevamento immediato manovre: {os.path.basename(self.priority_video)}...")
            self._process_maneuvers_for_video(self.priority_video, detector, man_detector)

        total_clips = len(self.video_files)
        start_time = time.time()
        clips_done = 0

        # 🥈 PRIORITÀ 2: Riconoscimento nomi & radio su tutte le clip
        for i, vf in enumerate(self.video_files):
            if self._is_cancelled:
                return

            # Se nel frattempo l'utente ha aperto un video specifico nel player, processa le sue manovre subito!
            if self._requested_priority:
                p_vid = self._requested_priority
                self._requested_priority = None
                self._process_maneuvers_for_video(p_vid, detector, man_detector)

            fname = os.path.basename(vf)
            sc = SidecarData(vf)

            # Se già analizzato nei metadati lo carica mantenendo la confidenza reale o 100% se manuale
            if sc.pilot_name:
                calc_conf = 1.0 if sc.manual_override else (sc.confidence if sc.confidence > 0 else 0.90)
                phr_list = [sc.radio_phrase] if sc.radio_phrase else []
                m = VideoPilotMatch(
                    video_path=vf,
                    filename=fname,
                    detected_pilot=sc.pilot_name,
                    confidence=calc_conf,
                    matched_phrases=phr_list,
                    duration=0.0,
                    flight_number=sc.flight_number
                )
                self.clip_analyzed.emit(m)
                self.clip_progress.emit(vf, 100.0, 100.0)
                clips_done += 1
                continue

            self.status_update.emit(f"Ascolto radio: {fname} ({i+1}/{total_clips})...")

            def on_file_prog(curr_s, dur_s):
                if not self._is_cancelled:
                    self.clip_progress.emit(vf, curr_s, dur_s)

            try:
                m = detector.identify_pilot_from_audio(
                    vf,
                    progress_callback=on_file_prog,
                    is_cancelled_callback=lambda: self._is_cancelled
                )
                if self._is_cancelled:
                    return

                # Salva subito nei metadati
                sc.pilot_name = m.detected_pilot
                sc.flight_number = m.flight_number or 1
                sc.confidence = m.confidence
                if m.matched_phrases:
                    sc.radio_phrase = " | ".join(m.matched_phrases)
                sc.save()

                self.clip_analyzed.emit(m)
                self.clip_progress.emit(vf, 100.0, 100.0)

                # Rileva e salva anche le manovre
                if hasattr(m, "segments") and m.segments:
                    chaps = man_detector.detect_chapters(m.segments)
                    if chaps:
                        sc.chapters = [{
                            "title": ch.maneuver_name,
                            "start": round(ch.start_time, 2),
                            "end": round(ch.end_time, 2),
                            "instructor_command": ch.transcription_text,
                            "notes": ch.category
                        } for ch in chaps]
                        sc.save()
                        self.maneuvers_ready.emit(vf, sc.chapters)

            except Exception as e:
                print(f"[Worker] Errore su {fname}: {e}")

            clips_done += 1
            elapsed = time.time() - start_time
            avg_per_clip = elapsed / max(1, clips_done)
            remaining_clips = total_clips - clips_done
            est_remaining_sec = int(avg_per_clip * remaining_clips)
            est_total_sec = int(avg_per_clip * total_clips)

            pct = int((clips_done / total_clips) * 100)
            if remaining_clips > 0:
                m_rem = est_remaining_sec // 60
                s_rem = est_remaining_sec % 60
                m_tot = est_total_sec // 60
                s_tot = est_total_sec % 60
                eta_str = f"⏱ Tempo stimato: {m_rem:02d}m {s_rem:02d}s rimanenti / ~{m_tot:02d}m {s_tot:02d}s totale previsto ({clips_done}/{total_clips} clip)"
            else:
                m_el = int(elapsed) // 60
                s_el = int(elapsed) % 60
                eta_str = f"✅ Analisi completata in {m_el:02d}m {s_el:02d}s ({total_clips} clip)"

            self.overall_progress.emit(eta_str, pct)

        # 🥉 PRIORITÀ 3: Perfeziona manovre su tutte le clip se non ancora calcolate
        for vf in self.video_files:
            if self._is_cancelled:
                return
            sc = SidecarData(vf)
            if not sc.chapters:
                self._process_maneuvers_for_video(vf, detector, man_detector)

        self.status_update.emit("Analisi completata.")

# ------------------------------------------------------------------
# STILE GLOBALE MATERIAL DESIGN 3: "DARK SLATE & CYAN"
# ------------------------------------------------------------------
MD3_STYLESHEET = """
QMainWindow {
    background-color: #0b111e;
}

QWidget {
    color: #f1f5f9;
    font-family: 'Segoe UI Variable Display', 'Segoe UI', system-ui, -apple-system, sans-serif;
    font-size: 13px;
}

/* Sfondo trasparente per label per evitare bande nere orizzontali */
QLabel {
    background-color: transparent;
    color: #f1f5f9;
}

/* Card & Superfici Elevate */
QFrame#welcomeCard {
    background-color: #131b2e;
    border: 1px solid #23314f;
    border-radius: 16px;
}

QFrame#chaptersPanel {
    background-color: #131b2e;
    border: 1px solid #23314f;
    border-radius: 12px;
}

/* Campi di Inserimento Testo */
QLineEdit, QTextEdit {
    background-color: #1a253c;
    border: 1.5px solid #2a3b5c;
    color: #f8fafc;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: #0891b2;
}
QLineEdit:hover, QTextEdit:hover {
    border: 1.5px solid #3d517a;
}
QLineEdit:focus, QTextEdit:focus {
    border: 1.5px solid #06b6d4;
    background-color: #162033;
}

/* Pulsanti Material 3 Generali */
QPushButton {
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #2a3b5c;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #2a3b5c;
    border-color: #3d517a;
}
QPushButton:pressed {
    background-color: #162033;
}

/* Scrollbar Material */
QScrollBar:vertical {
    border: none;
    background: #0b111e;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #23314f;
    min-height: 25px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #06b6d4;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    height: 0px;
}

/* Tabelle Material 3 */
QTableWidget {
    background-color: #131b2e;
    color: #f8fafc;
    gridline-color: #1c273e;
    font-size: 13px;
    border: 1px solid #23314f;
    border-radius: 12px;
    selection-background-color: #193153;
    selection-color: #ffffff;
    outline: none;
}
QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #182338;
}
QTableWidget::item:selected {
    background-color: #193153;
}
QTableWidget::item:hover {
    background-color: #17223b;
}

/* Intestazioni Colonne */
QHeaderView::section {
    background-color: #0e1626;
    color: #38bdf8;
    font-weight: 700;
    font-size: 11px;
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid #06b6d4;
    border-right: 1px solid #1a253c;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

/* QSpinBox Material 3 */
QSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    background-color: #23314f;
    border-top-right-radius: 5px;
    border-bottom: 1px solid #1a253c;
}
QSpinBox::up-button:hover {
    background-color: #0891b2;
}
QSpinBox::up-arrow {
    image: url(\"\"\" + ARROW_UP_PATH + \"\"\");
    width: 10px;
    height: 10px;
}
QSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    background-color: #23314f;
    border-bottom-right-radius: 5px;
}
QSpinBox::down-button:hover {
    background-color: #0891b2;
}
QSpinBox::down-arrow {
    image: url(\"\"\" + ARROW_DOWN_PATH + \"\"\");
    width: 10px;
    height: 10px;
}

/* Slider Video */
QSlider::groove:horizontal {
    height: 6px;
    background: #1c263d;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #06b6d4;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #06b6d4;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #22d3ee;
    border: 2px solid #ffffff;
}

/* Barre di Progresso Material */
QProgressBar {
    border: 1px solid #23314f;
    border-radius: 6px;
    text-align: center;
    background-color: #0b111e;
    color: #94a3b8;
    font-size: 11px;
    font-weight: 700;
}
QProgressBar::chunk {
    background-color: #06b6d4;
    border-radius: 5px;
}
"""

# ------------------------------------------------------------------
# FINESTRA PRINCIPALE: 3 SOLE FASI LINEARI (ZERO RUMORE)
# ------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SIV Video Analyzer")
        self.resize(1220, 760)

        # Applica il tema Material Design 3 Dark Slate & Cyan
        self.setStyleSheet(MD3_STYLESHEET)

        self.settings = QSettings("SIVVideoAnalyzer", "Settings")
        self.transcriber = SIVTranscriber(model_size="small")
        self.maneuver_detector = ManeuverDetector()
        self.video_files = []
        self.known_pilots = []
        self.pilot_gliders = {}
        self.current_video_path = None
        self.current_sidecar = None
        self.worker = None

        self._setup_ui()
        self._load_saved_preferences()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(18, 16, 18, 16)
        self.main_layout.setSpacing(12)

        # STACK A 3 SOLE SCHERMATE
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)

        # FASE 1: Accoglienza (Cartella + Piloti)
        self.page_welcome = self._create_page_welcome()
        self.stack.addWidget(self.page_welcome)

        # FASE 2: Tavolo di Lavoro (Tabella Voli Live)
        self.page_table = self._create_page_table()
        self.stack.addWidget(self.page_table)

        # FASE 3: Aula Debriefing (Player Focus)
        self.page_player = self._create_page_player()
        self.stack.addWidget(self.page_player)

        # Scorciatoie globali
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._toggle_play)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self._toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._handle_escape)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._seek(-5000))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._seek(5000))

    # ==============================================================
    # 🟢 SCHERMATA 1: ACCOGLIENZA / RAMPA DI LANCIO (MD3 CARD)
    # ==============================================================
    def _create_page_welcome(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedSize(660, 560)
        card.setObjectName("welcomeCard")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(36, 28, 36, 28)
        c_layout.setSpacing(10)

        # Header Material con Cyan Accent
        title = QLabel("Sessione Video SIV")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #38bdf8; letter-spacing: -0.5px;")
        c_layout.addWidget(title)

        subtitle = QLabel("Configura la cartella sorgente, la cartella di esportazione e i piloti iscritti.")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 13px; margin-bottom: 4px;")
        c_layout.addWidget(subtitle)

        # 1. Cartella Video Sorgente
        lbl_folder = QLabel("CARTELLA VIDEO O SCHEDA SD (SORGENTE)")
        lbl_folder.setStyleSheet("font-size: 11px; font-weight: 700; color: #cbd5e1; letter-spacing: 0.5px;")
        c_layout.addWidget(lbl_folder)

        f_row = QHBoxLayout()
        f_row.setSpacing(8)
        self.txt_folder = QLineEdit()
        self.txt_folder.setPlaceholderText("Es. D:\\DCIM\\100GOPRO o C:\\VoliSIV")
        btn_browse = QPushButton("📁 Sfoglia...")
        btn_browse.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2a3b5c;
                border-color: #06b6d4;
                color: #ffffff;
            }
        """)
        btn_browse.clicked.connect(self._browse_folder)
        f_row.addWidget(self.txt_folder, stretch=1)
        f_row.addWidget(btn_browse)
        c_layout.addLayout(f_row)

        # 2. Cartella Video Destinazione / Output Piloti
        lbl_output = QLabel("CARTELLA OUTPUT VIDEO ESPORTATI (PER I PILOTI)")
        lbl_output.setStyleSheet("font-size: 11px; font-weight: 700; color: #cbd5e1; letter-spacing: 0.5px; margin-top: 4px;")
        c_layout.addWidget(lbl_output)

        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        self.txt_output = QLineEdit()
        self.txt_output.setPlaceholderText("Es. C:\\Video_SIV_Finali (lascia vuoto per creare una cartella 'Output_Piloti')")
        btn_browse_out = QPushButton("📁 Sfoglia...")
        btn_browse_out.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2a3b5c;
                border-color: #06b6d4;
                color: #ffffff;
            }
        """)
        btn_browse_out.clicked.connect(self._browse_output_folder)
        out_row.addWidget(self.txt_output, stretch=1)
        out_row.addWidget(btn_browse_out)
        c_layout.addLayout(out_row)

        # 3. Piloti Iscritti & Vele
        lbl_pilots = QLabel("PILOTI E VELE DEL CORSO")
        lbl_pilots.setStyleSheet("font-size: 11px; font-weight: 700; color: #cbd5e1; letter-spacing: 0.5px; margin-top: 4px;")
        c_layout.addWidget(lbl_pilots)

        hint = QLabel("Formato: <i>Nome - Colore Vela</i> (es: <code>Mario Rossi - Rosso/Nero</code>)")
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        c_layout.addWidget(hint)

        from PyQt6.QtWidgets import QTextEdit
        self.txt_pilots = QTextEdit()
        self.txt_pilots.setPlaceholderText("Mario Rossi - Rosso/Nero\nLuca Bianchi - Blu/Bianco\nAlessandro Ame - Lime/Nero")
        self.txt_pilots.setFixedHeight(75)
        c_layout.addWidget(self.txt_pilots)

        # 4. Selezione Modello Whisper (Small vs Medium) & Configurazione Manovre
        m_row = QHBoxLayout()
        m_row.setSpacing(10)

        lbl_mod = QLabel("Precisione Analisi:")
        lbl_mod.setStyleSheet("font-size: 12px; font-weight: 600; color: #cbd5e1;")
        m_row.addWidget(lbl_mod)

        self.combo_model = QComboBox()
        self.combo_model.addItem("⚡ Bilanciata (Consigliata) - Whisper Small", "small")
        self.combo_model.addItem("🎯 Alta Precisione (Massima accuratezza) - Whisper Medium", "medium")
        self.combo_model.setStyleSheet("""
            QComboBox {
                background-color: #1a253c;
                border: 1.5px solid #2a3b5c;
                color: #f8fafc;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox:hover { border-color: #06b6d4; }
            QComboBox QAbstractItemView {
                background-color: #131b2e;
                color: #f8fafc;
                selection-background-color: #0891b2;
                border: 1px solid #23314f;
                padding: 4px;
            }
        """)
        m_row.addWidget(self.combo_model, stretch=1)

        self.btn_config_maneuvers = QPushButton("⚙️ Configura Manovre & Retry")
        self.btn_config_maneuvers.setStyleSheet("""
            QPushButton {
                background-color: #1a253c;
                border: 1.5px solid #2a3b5c;
                color: #38bdf8;
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #23314f;
                border-color: #38bdf8;
                color: #ffffff;
            }
        """)
        self.btn_config_maneuvers.setToolTip("Personalizza l'elenco manovre attive e le frasi di ripetizione ('fanne un'altra', 'riproviamo')")
        self.btn_config_maneuvers.clicked.connect(self._open_maneuvers_config)
        m_row.addWidget(self.btn_config_maneuvers)

        c_layout.addLayout(m_row)

        c_layout.addSpacing(6)

        # 5. Pulsante Avvio con stile Material 3 Filled Cyan/Emerald
        self.btn_launch = QPushButton("🚀  APRI REGISTRO VOLI")
        self.btn_launch.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
                padding: 12px 24px;
                border: none;
                border-radius: 10px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: #10b981;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.btn_launch.clicked.connect(self.start_session)
        c_layout.addWidget(self.btn_launch)

        layout.addWidget(card)
        return w

    # ==============================================================
    # 🟡 SCHERMATA 2: TAVOLO DI LAVORO (TABELLA VOLI MD3 LIVE)
    # ==============================================================
    def _create_page_table(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(14)
        layout.setContentsMargins(0, 0, 0, 0)

        # Barra superiore Material 3
        top = QHBoxLayout()
        top.setSpacing(12)

        btn_back_to_config = QPushButton("⬅ Torna alla Configurazione")
        btn_back_to_config.setStyleSheet("""
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
        btn_back_to_config.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        top.addWidget(btn_back_to_config)

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
            QPushButton:hover {
                background-color: #10b981;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        btn_export_all.setToolTip("Esporta tutti i voli dei piloti riconosciuti nella cartella di destinazione.")
        btn_export_all.clicked.connect(self._export_all_flights)
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
        btn_reset.clicked.connect(self.reset_analysis_data)
        top.addWidget(btn_reset)
        layout.addLayout(top)

        # Tabella Voli Material 3 (8 Colonne)
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

        return w

    # ==============================================================
    # 🔴 SCHERMATA 3: AULA DEBRIEFING (PLAYER MD3 FOCUS)
    # ==============================================================
    def _create_page_player(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header Player Material 3
        p_top = QHBoxLayout()
        btn_back = QPushButton("⬅ Torna alla Lista Voli")
        btn_back.setStyleSheet("""
            QPushButton {
                padding: 8px 18px;
                font-weight: 600;
                font-size: 13px;
                background-color: #131b2e;
                color: #cbd5e1;
                border: 1px solid #23314f;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #1c263d;
                color: #ffffff;
                border-color: #38bdf8;
            }
        """)
        btn_back.clicked.connect(self._back_to_table)
        p_top.addWidget(btn_back)

        self.lbl_flight_title = QLabel("Debriefing")
        self.lbl_flight_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #38bdf8; margin-left: 8px;")
        p_top.addWidget(self.lbl_flight_title)
        p_top.addStretch()

        self.btn_export_flight = QPushButton("🎬 Esporta Video Volo")
        self.btn_export_flight.setStyleSheet("""
            QPushButton {
                padding: 8px 18px;
                font-weight: 700;
                font-size: 13px;
                background-color: #059669;
                color: #ffffff;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #10b981;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.btn_export_flight.setToolTip("Esporta il video del volo corrente nella cartella Output con il file dei capitoli YouTube")
        self.btn_export_flight.clicked.connect(self._export_current_flight)
        p_top.addWidget(self.btn_export_flight)

        layout.addLayout(p_top)

        # Splitter: 75% Video - 25% Manovre
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Container Video
        vid_container = QWidget()
        v_layout = QVBoxLayout(vid_container)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(10)

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.video_widget = SIVVideoWidget()
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.video_widget.setStyleSheet("background-color: #000000; border-radius: 12px; border: 1px solid #1e293b;")
        self.video_widget.fullScreenChanged.connect(self._on_fullscreen_changed)
        self.video_widget.escape_pressed.connect(self._handle_escape)
        self.video_widget.toggle_fullscreen_requested.connect(self._toggle_fullscreen)
        self.video_widget.toggle_play_requested.connect(self._toggle_play)
        self.video_widget.seek_requested.connect(self._seek)
        self.media_player.setVideoOutput(self.video_widget)
        v_layout.addWidget(self.video_widget, stretch=1)

        # Controlli a una sola mano Material 3
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(10)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: 700;
                padding: 9px 24px;
                background-color: #0891b2;
                color: #ffffff;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #06b6d4; }
            QPushButton:pressed { background-color: #0e7490; }
        """)
        self.btn_play.clicked.connect(self._toggle_play)
        ctrl_bar.addWidget(self.btn_play)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("font-weight: 700; font-size: 13px; color: #94a3b8; min-width: 95px;")
        ctrl_bar.addWidget(self.lbl_time)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.media_player.setPosition)
        ctrl_bar.addWidget(self.slider)

        btn_seek_b = QPushButton("⏪ -5s")
        btn_seek_b.setStyleSheet("""
            QPushButton {
                padding: 8px 14px;
                font-weight: 600;
                background-color: #131b2e;
                border: 1px solid #23314f;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #1c263d; border-color: #38bdf8; }
        """)
        btn_seek_b.clicked.connect(lambda: self._seek(-5000))
        ctrl_bar.addWidget(btn_seek_b)

        btn_seek_f = QPushButton("⏩ +5s")
        btn_seek_f.setStyleSheet("""
            QPushButton {
                padding: 8px 14px;
                font-weight: 600;
                background-color: #131b2e;
                border: 1px solid #23314f;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #1c263d; border-color: #38bdf8; }
        """)
        btn_seek_f.clicked.connect(lambda: self._seek(5000))
        ctrl_bar.addWidget(btn_seek_f)

        self.btn_fullscreen = QPushButton("⛶ Schermo Intero (F)")
        self.btn_fullscreen.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                font-weight: 600;
                background-color: #131b2e;
                color: #f1f5f9;
                border: 1px solid #23314f;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #1c263d; border-color: #06b6d4; }
        """)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        ctrl_bar.addWidget(self.btn_fullscreen)

        v_layout.addLayout(ctrl_bar)
        splitter.addWidget(vid_container)

        # Container Manovre Card
        right_panel = QFrame()
        right_panel.setObjectName("chaptersPanel")
        r_layout = QVBoxLayout(right_panel)
        r_layout.setContentsMargins(14, 14, 14, 14)
        r_layout.setSpacing(10)

        lbl_ch_title = QLabel("CAPITOLI & MANOVRE")
        lbl_ch_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #38bdf8; letter-spacing: 0.5px;")
        r_layout.addWidget(lbl_ch_title)

        self.table_chapters = QTableWidget(0, 2)
        self.table_chapters.setHorizontalHeaderLabels(["Tempo", "Manovra"])
        self.table_chapters.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_chapters.verticalHeader().setVisible(False)
        self.table_chapters.setShowGrid(False)
        self.table_chapters.cellDoubleClicked.connect(self._on_chapter_clicked)
        r_layout.addWidget(self.table_chapters)

        btn_add_ch = QPushButton("➕ Segna Manovra qui")
        btn_add_ch.setStyleSheet("""
            QPushButton {
                padding: 10px;
                font-weight: 700;
                font-size: 13px;
                background-color: #0891b2;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #06b6d4; }
            QPushButton:pressed { background-color: #0e7490; }
        """)
        btn_add_ch.clicked.connect(self._add_chapter_here)
        r_layout.addWidget(btn_add_ch)

        splitter.addWidget(right_panel)
        splitter.setSizes([840, 320])
        layout.addWidget(splitter, stretch=1)

        self.media_player.positionChanged.connect(self._on_player_pos_changed)
        self.media_player.durationChanged.connect(lambda dur: self.slider.setRange(0, dur))

        return w

    # ==============================================================
    # LOGICA DI CONTROLLO & EVENTI
    # ==============================================================
    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella video SIV (Sorgente)", self.txt_folder.text().strip() or "")
        if d:
            self.txt_folder.setText(d)
            self._save_preferences()

    def _browse_output_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella Output Video Piloti", self.txt_output.text().strip() or "")
        if d:
            self.txt_output.setText(d)
            self._save_preferences()

    def _load_saved_preferences(self):
        saved_f = self.settings.value("source_dir", "")
        if saved_f and os.path.exists(saved_f):
            self.txt_folder.setText(saved_f)

        saved_out = self.settings.value("output_dir", "")
        if saved_out:
            self.txt_output.setText(saved_out)

        saved_p = self.settings.value("pilots", "")
        if saved_p:
            if hasattr(self.txt_pilots, "setPlainText"):
                self.txt_pilots.setPlainText(saved_p)
            else:
                self.txt_pilots.setText(saved_p)

        saved_mod = self.settings.value("whisper_model", "small")
        if saved_mod:
            idx = self.combo_model.findData(saved_mod)
            if idx >= 0:
                self.combo_model.setCurrentIndex(idx)

    def _save_preferences(self):
        self.settings.setValue("source_dir", self.txt_folder.text().strip())
        self.settings.setValue("output_dir", self.txt_output.text().strip())
        pilots_txt = self.txt_pilots.toPlainText().strip() if hasattr(self.txt_pilots, "toPlainText") else self.txt_pilots.text().strip()
        self.settings.setValue("pilots", pilots_txt)
        selected_model = self.combo_model.currentData() or "small"
        self.settings.setValue("whisper_model", selected_model)
        self.settings.sync()

    def _open_maneuvers_config(self):
        dlg = ManeuversConfigDialog(self.maneuver_detector, self)
        dlg.exec()

    def start_session(self):
        folder = self.txt_folder.text().strip()
        if not folder or not os.path.exists(folder):
            QMessageBox.warning(self, "Attenzione", "Seleziona una cartella video valida.")
            return

        self._save_preferences()

        # Parsing Piloti e Vele: ogni riga può essere "Nome - Colore" oppure "Nome, Colore"
        self.pilot_gliders = {}
        pilot_names = []
        raw_text = self.txt_pilots.toPlainText() if hasattr(self.txt_pilots, "toPlainText") else self.txt_pilots.text()
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "-" in line:
                parts = line.split("-", 1)
                p_name, g_color = parts[0].strip(), parts[1].strip()
            elif "," in line:
                parts = line.split(",", 1)
                p_name, g_color = parts[0].strip(), parts[1].strip()
            else:
                p_name, g_color = line, ""
            
            if p_name:
                pilot_names.append(p_name)
                self.pilot_gliders[p_name.lower()] = g_color

        # Salva i nomi piloti per i menu a tendina
        self.known_pilots = list(pilot_names)

        valid_exts = {".mp4", ".mov", ".avi", ".mkv", ".mts", ".m2ts"}
        self.video_files = []
        for root, _, files in os.walk(folder):
            for file in files:
                if os.path.splitext(file)[1].lower() in valid_exts:
                    self.video_files.append(os.path.join(root, file))

        # Ordina cronologicamente i video (prima per creation time / mtime, poi per nome)
        try:
            self.video_files = sorted(
                list(set(self.video_files)),
                key=lambda vf: (get_video_creation_time(vf), os.path.basename(vf).lower())
            )
        except Exception:
            self.video_files = sorted(list(set(self.video_files)))

        if not self.video_files:
            QMessageBox.warning(self, "Nessun Video", "Nessun file video trovato nella cartella specificata.")
            return

        # 1. Cambia IMMEDIATAMENTE schermata per feedback istantaneo (< 10ms)
        self.table_flights.setRowCount(0)
        self.lbl_table_header.setText(f"<b>Sessione:</b> {os.path.basename(folder)} ({len(self.video_files)} video)")
        self.stack.setCurrentIndex(1)
        QApplication.processEvents()

        # 2. Carica istantaneamente i metadati esistenti salvati nei sidecar JSON
        videos_to_process = []
        for vf in self.video_files:
            sc = SidecarData(vf)
            # Leggi data e ora salvata nel sidecar; se non presente, estraila e salvala per accessi futuri istantanei
            rec_dt = sc.recorded_at
            if not rec_dt:
                rec_dt = get_formatted_video_datetime(vf)
                if rec_dt and rec_dt != "—":
                    sc.recorded_at = rec_dt
                    sc.save()

            glider_col = sc.glider or self.pilot_gliders.get(sc.pilot_name.lower(), "")
            if sc.pilot_name:
                calc_conf = 1.0 if sc.manual_override else (sc.confidence if sc.confidence > 0 else 0.90)
                phrase = sc.radio_phrase or ("— (Nessuna chiamata radio)" if not sc.manual_override else "Assegnato manualmente")
                self._add_flight_row(vf, sc.pilot_name, sc.flight_number or 1, glider_col, phrase, is_confirmed=True, confidence=calc_conf, recorded_at=rec_dt)
            else:
                self._add_flight_row(vf, "In attesa...", 1, "", "In coda di analisi...", is_confirmed=False, recorded_at=rec_dt)
                videos_to_process.append(vf)

        # Avvia worker background non bloccante per quelli mancanti
        if videos_to_process:
            selected_model = self.combo_model.currentData() or "small"
            self.transcriber.set_model_size(selected_model)
            self.progress_overall.setValue(0)
            self.progress_overall.setVisible(True)
            self.worker = AnalysisWorker(
                video_files=videos_to_process,
                pilot_names=pilot_names,
                transcriber=self.transcriber,
                maneuver_detector=self.maneuver_detector
            )
            self.worker.clip_analyzed.connect(self._on_clip_analyzed)
            self.worker.clip_progress.connect(self._on_clip_progress)
            self.worker.overall_progress.connect(self._on_overall_progress)
            self.worker.status_update.connect(self.lbl_worker_status.setText)
            self.worker.maneuvers_ready.connect(self._on_maneuvers_ready)
            self.worker.start()
        else:
            self.progress_overall.setVisible(False)
            self.lbl_worker_status.setText("Tutti i video sono già stati analizzati.")

    def reset_analysis_data(self):
        """Cancella i dati salvati e svuota la cache delle trascrizioni per rieseguire l'analisi da zero."""
        if not self.video_files:
            return

        reply = QMessageBox.question(
            self,
            "Conferma Reset Analisi",
            "Vuoi cancellare i dati di riconoscimento per questa sessione e rieseguire l'analisi da zero?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Ferma eventuale worker in corso
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.worker.wait(1000)

        # Rimuove i file sidecar .json associati ai video
        deleted_count = 0
        for vf in self.video_files:
            sc_path = os.path.splitext(vf)[0] + ".json"
            if os.path.exists(sc_path):
                try:
                    os.remove(sc_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"[Reset] Errore rimozione {sc_path}: {e}")

        # Svuota eventuale cache locale temp
        if os.path.exists("temp"):
            import glob
            for f in glob.glob("temp/*_cache.json") + glob.glob("temp/*.wav"):
                try:
                    os.remove(f)
                except Exception:
                    pass

        # Riavvia la sessione con tabella pulita
        self.start_session()

    def _calculate_auto_flight_number(self, pilot_name: str, current_row: int) -> int:
        """
        Calcola automaticamente il numero progressivo di volo per un pilota
        in base alla posizione cronologica dei suoi video nella tabella.
        """
        if not pilot_name or pilot_name in ["In attesa...", "Da Assegnare"]:
            return 1

        count = 0
        for r in range(self.table_flights.rowCount()):
            # Pilota della riga r (Colonna 3)
            p_combo = self.table_flights.cellWidget(r, 3)
            row_pilot = p_combo.currentText() if isinstance(p_combo, QComboBox) else ""
            if row_pilot.strip().lower() == pilot_name.strip().lower():
                count += 1
                if r == current_row:
                    return count
        return max(1, count)

    def _add_flight_row(self, video_path: str, pilot: str, flight_num: int, glider: str, phrases: str, is_confirmed: bool, confidence: float = 1.0, recorded_at: str = ""):
        row = self.table_flights.rowCount()
        self.table_flights.blockSignals(True)
        self.table_flights.insertRow(row)

        # Colonna 0: File Video
        fname = os.path.basename(video_path)
        item_file = QTableWidgetItem(fname)
        item_file.setFlags(item_file.flags() ^ Qt.ItemFlag.ItemIsEditable)
        item_file.setData(Qt.ItemDataRole.UserRole, video_path)
        self.table_flights.setItem(row, 0, item_file)

        # Colonna 1: Data e Ora di Registrazione (persistita e formattata)
        if not recorded_at:
            recorded_at = get_formatted_video_datetime(video_path)
        item_dt = QTableWidgetItem(recorded_at)
        item_dt.setFlags(item_dt.flags() ^ Qt.ItemFlag.ItemIsEditable)
        item_dt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_dt.setForeground(QBrush(QColor("#94a3b8")))
        item_dt.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.table_flights.setItem(row, 1, item_dt)

        # Colonna 2: Volo N° con QSpinBox Material 3
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
            QSpinBox::up-button:hover {{
                background-color: #0891b2;
            }}
            QSpinBox::up-arrow {{
                image: url("{ARROW_UP_PATH}");
                width: 10px;
                height: 10px;
            }}
            QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                background-color: #23314f;
                border-bottom-right-radius: 5px;
            }}
            QSpinBox::down-button:hover {{
                background-color: #0891b2;
            }}
            QSpinBox::down-arrow {{
                image: url("{ARROW_DOWN_PATH}");
                width: 10px;
                height: 10px;
            }}
        """)
        spin_flight.valueChanged.connect(lambda val, r=row, p=video_path: self._on_flight_spin_changed(r, p, val))
        self.table_flights.setCellWidget(row, 2, spin_flight)

        # Colonna 3: Pilota Assegnato con QComboBox Material 3
        combo_pilot = QComboBox()
        combo_pilot.setEditable(True)
        combo_pilot.addItem("Da Assegnare")
        for p in self.known_pilots:
            if p not in ["Da Assegnare"]:
                combo_pilot.addItem(p)

        # Se il pilota non è ancora nella lista, aggiungilo
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

        # Colonna 5: Esito / Certezza (Barra durante l'analisi, Badge a fine analisi)
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

        # Colonna 7: Debriefing Material 3 Button
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
        btn_watch.clicked.connect(lambda _, p=video_path: self._open_debriefing(p))
        self.table_flights.setCellWidget(row, 7, btn_watch)
        self.table_flights.blockSignals(False)

    def _set_certainty_badge(self, row: int, confidence: float):
        """Imposta un badge didattico chiaro al posto della barra al termine dell'analisi."""
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

    def _on_clip_progress(self, video_path: str, curr_sec: float, total_sec: float):
        """Aggiorna la progressione percentuale sulla specifica riga del video in analisi."""
        pct = int(min(100.0, (curr_sec / max(0.1, total_sec)) * 100.0)) if total_sec > 0 else 50
        for r in range(self.table_flights.rowCount()):
            item = self.table_flights.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == video_path:
                bar = self.table_flights.cellWidget(r, 5)
                if isinstance(bar, QProgressBar):
                    bar.setValue(pct)
                break

    def _on_overall_progress(self, eta_text: str, percent: int):
        """Aggiorna il banner superiore con il tempo stimato residuo e la percentuale complessiva."""
        self.lbl_worker_status.setText(eta_text)
        self.progress_overall.setVisible(True)
        self.progress_overall.setValue(percent)
        if percent >= 100:
            self.progress_overall.setStyleSheet(self.progress_overall.styleSheet() + "QProgressBar::chunk { background-color: #16a34a; }")

    def _on_clip_analyzed(self, match: VideoPilotMatch):
        for r in range(self.table_flights.rowCount()):
            item = self.table_flights.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == match.video_path:
                self.table_flights.blockSignals(True)

                # 1. Aggiorna pilota nel menu a tendina (Colonna 3)
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

                # 2. Aggiorna numero di volo (Colonna 2):
                spin_volo = self.table_flights.cellWidget(r, 2)
                final_flight_num = match.flight_number
                if not final_flight_num or final_flight_num <= 0:
                    final_flight_num = self._calculate_auto_flight_number(match.detected_pilot, r)

                if isinstance(spin_volo, QSpinBox):
                    spin_volo.blockSignals(True)
                    spin_volo.setValue(final_flight_num)
                    spin_volo.blockSignals(False)

                # 3. Aggiorna vela abbinata (Colonna 4)
                glider_val = self.pilot_gliders.get(match.detected_pilot.lower(), "")
                g_item = QTableWidgetItem(glider_val)
                g_item.setForeground(QBrush(QColor("#38bdf8")))
                self.table_flights.setItem(r, 4, g_item)

                # 4. Sostituisce la barra di progresso con il badge di certezza (Colonna 5)
                conf = getattr(match, "confidence", 1.0) or 1.0
                self._set_certainty_badge(r, conf)

                # 5. Chiamata Radio (Colonna 6)
                phr = " | ".join(match.matched_phrases) if match.matched_phrases else "—"
                self.table_flights.setItem(r, 6, QTableWidgetItem(phr))
                self.table_flights.blockSignals(False)

                # Salva i dati effettivi nel sidecar
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
        """Salva immediatamente il numero di volo impostato manualmente tramite lo spinbox."""
        if not video_path or not os.path.exists(video_path):
            return
        sc = SidecarData(video_path)
        sc.flight_number = value
        sc.save()

    def _on_pilot_combo_changed(self, row: int, video_path: str, pilot_name: str):
        """Gestisce il cambio pilota dal menu a tendina o testo libero, aggiornando vela e certezza."""
        if not video_path or not os.path.exists(video_path):
            return
        pilot_name = pilot_name.strip()
        sc = SidecarData(video_path)
        sc.pilot_name = pilot_name
        sc.manual_override = True
        sc.confidence = 1.0

        # Aggiorna vela abbinata se nota (Colonna 4)
        glider_val = self.pilot_gliders.get(pilot_name.lower(), "")
        if glider_val:
            sc.glider = glider_val
            g_item = self.table_flights.item(row, 4)
            if g_item:
                g_item.setText(glider_val)
            else:
                self.table_flights.setItem(row, 4, QTableWidgetItem(glider_val))

        # Ricalcola automaticamente il numero di volo cronologico se non già specificato (Colonna 2)
        spin_volo = self.table_flights.cellWidget(row, 2)
        if isinstance(spin_volo, QSpinBox):
            auto_num = self._calculate_auto_flight_number(pilot_name, row)
            spin_volo.blockSignals(True)
            spin_volo.setValue(auto_num)
            spin_volo.blockSignals(False)
            sc.flight_number = auto_num

        sc.save()

        # Rifletti immediatamente certezza al 100% (intervento manuale)
        self._set_certainty_badge(row, 1.0)

    def _on_table_cell_edited(self, row: int, col: int):
        """Salva modifiche manuali su celle residue (es. Colonna 4: Vela)."""
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
            self._open_debriefing(v_path)

    # ==============================================================
    # DEBRIEFING & PLAYER
    # ==============================================================
    def _open_debriefing(self, video_path: str):
        self.current_video_path = video_path
        self.current_sidecar = SidecarData(video_path)

        pilot = self.current_sidecar.pilot_name or "Pilota"
        fl = f" - Volo {self.current_sidecar.flight_number}" if self.current_sidecar.flight_number else ""
        self.lbl_flight_title.setText(f"{pilot}{fl} ({os.path.basename(video_path)})")

        self.media_player.setSource(QUrl.fromLocalFile(video_path))
        self.media_player.play()
        self.btn_play.setText("⏸ Pausa")
        self._refresh_chapters_table()

        # PRIORITÀ ASSOLUTA: Se il worker è in esecuzione, richiedi subito l'analisi manovre di questa clip
        if self.worker and self.worker.isRunning():
            self.worker.request_priority_video(video_path)

        self.stack.setCurrentIndex(2)

    def _on_maneuvers_ready(self, video_path: str, chapters: list):
        """Riceve le manovre calcolate dal worker: se la clip aperta è questa, aggiorna subito la tabella capitoli."""
        if self.current_video_path == video_path:
            if self.current_sidecar:
                self.current_sidecar.chapters = chapters
            self._refresh_chapters_table()

    def _export_current_flight(self):
        """Esporta il volo attualmente aperto nel debriefing player in MP4 con i capitoli YouTube."""
        if not self.current_video_path or not os.path.exists(self.current_video_path):
            QMessageBox.warning(self, "Attenzione", "Nessun video valido aperto per l'esportazione.")
            return

        out_dir = self.txt_output.text().strip()
        if not out_dir:
            source_dir = self.txt_folder.text().strip()
            out_dir = os.path.join(source_dir if source_dir else os.path.dirname(self.current_video_path), "Output_Piloti")

        sc = self.current_sidecar or SidecarData(self.current_video_path)
        p_name = sc.pilot_name or "Pilota_Sconosciuto"
        fl_num = sc.flight_number or 1

        from core.flight_grouper import VideoExporter
        self.btn_export_flight.setEnabled(False)
        self.btn_export_flight.setText("⏳ Esportazione in corso...")
        QApplication.processEvents()

        try:
            target_mp4 = VideoExporter.export_flight_video(
                output_dir=out_dir,
                pilot_name=p_name,
                flight_number=fl_num,
                video_paths=[self.current_video_path],
                chapters=sc.chapters
            )
            QMessageBox.information(
                self,
                "Esportazione Completata",
                f"Video esportato con successo!\n\nFile salvato in:\n{target_mp4}\n\nÈ stato generato anche il file dei capitoli YouTube."
            )
        except Exception as e:
            QMessageBox.critical(self, "Errore Esportazione", f"Impossibile esportare il video:\n{e}")
        finally:
            self.btn_export_flight.setEnabled(True)
            self.btn_export_flight.setText("🎬 Esporta Video Volo")

    def _export_all_flights(self):
        """Esporta tutti i voli dei piloti riconosciuti nella cartella di destinazione."""
        if self.table_flights.rowCount() == 0:
            QMessageBox.warning(self, "Nessun Volo", "Nessun volo presente nella sessione da esportare.")
            return

        out_dir = self.txt_output.text().strip()
        if not out_dir:
            source_dir = self.txt_folder.text().strip()
            out_dir = os.path.join(source_dir, "Output_Piloti") if source_dir else "Output_Piloti"

        # Raccoglie i video raggruppati per (pilota, volo_num)
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

        if not flights_map:
            QMessageBox.warning(self, "Attenzione", "Nessun volo ha un pilota assegnato valido da esportare.")
            return

        from core.flight_grouper import VideoExporter
        exported_count = 0
        errors = []

        self.lbl_worker_status.setText("⏳ Esportazione video in corso...")
        QApplication.processEvents()

        for (p_name, fl_num), v_paths in flights_map.items():
            try:
                # Recupera i capitoli dal primo video o unione
                sc = SidecarData(v_paths[0])
                VideoExporter.export_flight_video(
                    output_dir=out_dir,
                    pilot_name=p_name,
                    flight_number=fl_num,
                    video_paths=v_paths,
                    chapters=sc.chapters
                )
                exported_count += 1
            except Exception as e:
                errors.append(f"{p_name} Volo {fl_num}: {e}")

        self.lbl_worker_status.setText(f"Esportazione completata ({exported_count} voli)")
        if errors:
            QMessageBox.warning(
                self,
                "Esportazione Parziale",
                f"Esportati {exported_count} voli su {len(flights_map)}.\nErrori riscontrati:\n" + "\n".join(errors)
            )
        else:
            QMessageBox.information(
                self,
                "Esportazione Completata",
                f"Tutti i {exported_count} voli sono stati esportati con successo in:\n{out_dir}\n\nCon i relativi file dei capitoli YouTube!"
            )

    def _back_to_table(self):
        self.media_player.pause()
        self.stack.setCurrentIndex(1)

    def _toggle_play(self):
        if self.stack.currentIndex() != 2:
            return
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.btn_play.setText("▶ Play")
        else:
            self.media_player.play()
            self.btn_play.setText("⏸ Pausa")

    def _seek(self, offset_ms: int):
        if self.stack.currentIndex() != 2:
            return
        new_pos = max(0, min(self.media_player.position() + offset_ms, self.media_player.duration()))
        self.media_player.setPosition(new_pos)

    def _toggle_fullscreen(self):
        if self.stack.currentIndex() != 2:
            return
        if self.video_widget.isFullScreen():
            self.video_widget.setFullScreen(False)
            self.btn_fullscreen.setText("⛶ Schermo Intero (F)")
        else:
            self.video_widget.setFullScreen(True)
            self.btn_fullscreen.setText("Normale (ESC)")

    def _handle_escape(self):
        if self.video_widget.isFullScreen():
            self.video_widget.setFullScreen(False)
            self.btn_fullscreen.setText("⛶ Schermo Intero (F)")
        elif self.stack.currentIndex() == 2:
            self._back_to_table()

    def _on_fullscreen_changed(self, is_full: bool):
        if is_full:
            self.btn_fullscreen.setText("Normale (ESC)")
        else:
            self.btn_fullscreen.setText("⛶ Schermo Intero (F)")

    def _on_player_pos_changed(self, pos_ms: int):
        self.slider.setValue(pos_ms)
        pos_s = pos_ms // 1000
        dur_s = self.media_player.duration() // 1000
        self.lbl_time.setText(f"{pos_s//60:02d}:{pos_s%60:02d} / {dur_s//60:02d}:{dur_s%60:02d}")

    def _refresh_chapters_table(self):
        self.table_chapters.setRowCount(0)
        if not self.current_sidecar:
            return
        chaps = self.current_sidecar.chapters
        self.table_chapters.setRowCount(len(chaps))
        for r, ch in enumerate(chaps):
            start_s = int(ch.get("start", 0))
            time_str = f"{start_s//60:02d}:{start_s%60:02d}"
            item_t = QTableWidgetItem(time_str)
            item_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_chapters.setItem(r, 0, item_t)
            self.table_chapters.setItem(r, 1, QTableWidgetItem(ch.get("title", "")))

    def _on_chapter_clicked(self, row: int, col: int):
        if not self.current_sidecar or row >= len(self.current_sidecar.chapters):
            return
        ch = self.current_sidecar.chapters[row]
        start_ms = int(ch.get("start", 0) * 1000)
        self.media_player.setPosition(start_ms)
        self.media_player.play()
        self.btn_play.setText("⏸ Pausa")

    def _add_chapter_here(self):
        if not self.current_sidecar:
            return
        curr_s = self.media_player.position() / 1000.0
        active_mans = self.maneuver_detector.active_maneuvers if self.maneuver_detector else []
        dlg = AddChapterQuickDialog(current_seconds=curr_s, active_maneuvers=active_mans, parent=self)
        if dlg.exec():
            title = dlg.selected_title
            if title:
                self.current_sidecar.add_chapter(
                    title=title,
                    start=round(curr_s, 2),
                    end=round(curr_s + 15.0, 2),
                    notes=dlg.selected_category
                )
                self.current_sidecar.save()
                self._refresh_chapters_table()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.worker.wait(1500)
        event.accept()
