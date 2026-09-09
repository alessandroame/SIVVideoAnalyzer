import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QSlider, QFrame, QSplitter, QProgressBar
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from core.sidecar_manager import SidecarData
from ui.add_chapter_dialog import AddChapterQuickDialog
from ui.detect_engine_dialog import DetectManeuversEngineDialog
from ui.transcription_inspector_dialog import TranscriptionInspectorDialog
from ui.wing_color_inspector_dialog import WingColorInspectorDialog

class SIVVideoWidget(QVideoWidget):
    """QVideoWidget con gestione integrata della tastiera in modalità a tutto schermo."""
    escape_pressed = pyqtSignal()
    toggle_fullscreen_requested = pyqtSignal()
    toggle_play_requested = pyqtSignal()
    seek_requested = pyqtSignal(int)

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


class DebriefingPlayerWidget(QWidget):
    """Componente autonomo per l'Aula Debriefing (Player video & Timeline Capitoli)."""
    back_to_table_requested = pyqtSignal()
    export_current_flight_requested = pyqtSignal()
    detect_maneuvers_requested = pyqtSignal(str, str)  # video_path, model_name

    def __init__(self, maneuver_detector=None, parent=None):
        super().__init__(parent)
        self.maneuver_detector = maneuver_detector
        self.current_video_path = None
        self.current_sidecar = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header Player
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
        btn_back.clicked.connect(self._on_back_clicked)
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
            QPushButton:hover { background-color: #10b981; }
            QPushButton:pressed { background-color: #047857; }
        """)
        self.btn_export_flight.setToolTip("Esporta il video del volo corrente nella cartella Output con il file dei capitoli YouTube")
        self.btn_export_flight.clicked.connect(self.export_current_flight_requested.emit)
        p_top.addWidget(self.btn_export_flight)

        layout.addLayout(p_top)

        # Splitter: Video e Manovre
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
        self.video_widget.escape_pressed.connect(self.handle_escape)
        self.video_widget.toggle_fullscreen_requested.connect(self.toggle_fullscreen)
        self.video_widget.toggle_play_requested.connect(self.toggle_play)
        self.video_widget.seek_requested.connect(self.seek)
        self.media_player.setVideoOutput(self.video_widget)
        v_layout.addWidget(self.video_widget, stretch=1)

        # Controlli playback
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
        self.btn_play.clicked.connect(self.toggle_play)
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
        btn_seek_b.clicked.connect(lambda: self.seek(-5000))
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
        btn_seek_f.clicked.connect(lambda: self.seek(5000))
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
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        ctrl_bar.addWidget(self.btn_fullscreen)

        v_layout.addLayout(ctrl_bar)
        splitter.addWidget(vid_container)

        # Pannello Manovre
        right_panel = QFrame()
        right_panel.setObjectName("chaptersPanel")
        r_layout = QVBoxLayout(right_panel)
        r_layout.setContentsMargins(14, 14, 14, 14)
        r_layout.setSpacing(10)

        lbl_ch_title = QLabel("CAPITOLI & MANOVRE")
        lbl_ch_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #38bdf8; letter-spacing: 0.5px;")
        r_layout.addWidget(lbl_ch_title)

        # Status & Progresso Rilevamento Manovre
        self.lbl_maneuver_status = QLabel("")
        self.lbl_maneuver_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #fbbf24;")
        self.lbl_maneuver_status.setWordWrap(True)
        self.lbl_maneuver_status.setVisible(False)
        r_layout.addWidget(self.lbl_maneuver_status)

        self.prog_maneuver = QProgressBar()
        self.prog_maneuver.setRange(0, 100)
        self.prog_maneuver.setFixedHeight(8)
        self.prog_maneuver.setTextVisible(False)
        self.prog_maneuver.setStyleSheet("""
            QProgressBar {
                border: 1px solid #1e293b;
                border-radius: 4px;
                background-color: #0b111e;
            }
            QProgressBar::chunk {
                background-color: #06b6d4;
                border-radius: 3px;
            }
        """)
        self.prog_maneuver.setVisible(False)
        r_layout.addWidget(self.prog_maneuver)

        self.table_chapters = QTableWidget(0, 2)
        self.table_chapters.setHorizontalHeaderLabels(["Tempo", "Manovra"])
        self.table_chapters.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_chapters.verticalHeader().setVisible(False)
        self.table_chapters.setShowGrid(False)
        self.table_chapters.cellDoubleClicked.connect(self._on_chapter_clicked)
        r_layout.addWidget(self.table_chapters)

        self.btn_detect_maneuvers = QPushButton("🎯 Rileva Manovre...")
        self.btn_detect_maneuvers.setStyleSheet("""
            QPushButton {
                padding: 10px;
                font-weight: 700;
                font-size: 13px;
                background-color: #0284c7;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #0369a1; }
            QPushButton:pressed { background-color: #075985; }
        """)
        self.btn_detect_maneuvers.setToolTip("Scegli il motore Whisper ed esegui il rilevamento automatico dei comandi radio e delle manovre.")
        self.btn_detect_maneuvers.clicked.connect(self._on_detect_maneuvers_clicked)
        r_layout.addWidget(self.btn_detect_maneuvers)

        btn_add_ch = QPushButton("➕ Segna Manovra qui")
        btn_add_ch.setStyleSheet("""
            QPushButton {
                padding: 9px;
                font-weight: 600;
                font-size: 12px;
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #334155; color: #ffffff; }
            QPushButton:pressed { background-color: #0f172a; }
        """)
        btn_add_ch.clicked.connect(self._add_chapter_here)
        r_layout.addWidget(btn_add_ch)

        self.btn_inspect_transcription = QPushButton("🔍 Leggi Trascrizione Whisper")
        self.btn_inspect_transcription.setStyleSheet("""
            QPushButton {
                padding: 7px;
                font-weight: 600;
                font-size: 11px;
                background-color: transparent;
                color: #94a3b8;
                border: 1px dashed #334155;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1e293b; color: #38bdf8; border-color: #38bdf8; }
        """)
        self.btn_inspect_transcription.setToolTip("Visualizza la trascrizione esatta riconosciuta da Whisper per capire quali parole radio sono state captate.")
        self.btn_inspect_transcription.clicked.connect(self._on_inspect_transcription_clicked)
        r_layout.addWidget(self.btn_inspect_transcription)

        self.btn_inspect_wing_color = QPushButton("🎨 Diagnostica Colori Vela")
        self.btn_inspect_wing_color.setStyleSheet("""
            QPushButton {
                padding: 7px;
                font-weight: 600;
                font-size: 11px;
                background-color: transparent;
                color: #94a3b8;
                border: 1px dashed #334155;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1e293b; color: #f59e0b; border-color: #f59e0b; }
        """)
        self.btn_inspect_wing_color.setToolTip("Ispeziona i fotogrammi estratti, i pixel campionati e i colori identificati per questa vela.")
        self.btn_inspect_wing_color.clicked.connect(self._on_inspect_wing_color_clicked)
        r_layout.addWidget(self.btn_inspect_wing_color)

        splitter.addWidget(right_panel)
        splitter.setSizes([840, 320])
        layout.addWidget(splitter, stretch=1)

        self.media_player.positionChanged.connect(self._on_player_pos_changed)
        self.media_player.durationChanged.connect(lambda dur: self.slider.setRange(0, dur))

    def set_maneuver_progress(self, video_path: str, text: str, percent: int):
        if self.current_video_path == video_path:
            self.lbl_maneuver_status.setVisible(True)
            self.lbl_maneuver_status.setText(f"⏳ {text}")
            if percent < 100:
                self.prog_maneuver.setVisible(True)
                self.prog_maneuver.setValue(percent)
                self.lbl_maneuver_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #fbbf24;")
            else:
                self.prog_maneuver.setVisible(False)
                self.lbl_maneuver_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #10b981;")
                self.lbl_maneuver_status.setText(f"✅ {text}")

    def hide_maneuver_progress(self):
        self.lbl_maneuver_status.setVisible(False)
        self.prog_maneuver.setVisible(False)

    def open_video(self, video_path: str):
        self.current_video_path = video_path
        self.current_sidecar = SidecarData(video_path)

        pilot = self.current_sidecar.pilot_name or "Pilota"
        fl = f" - Volo {self.current_sidecar.flight_number}" if self.current_sidecar.flight_number else ""
        self.lbl_flight_title.setText(f"{pilot}{fl} ({os.path.basename(video_path)})")

        self.media_player.setSource(QUrl.fromLocalFile(video_path))
        self.media_player.play()
        self.btn_play.setText("⏸ Pausa")
        if self.current_sidecar.chapters:
            self.hide_maneuver_progress()
        else:
            self.set_maneuver_progress(video_path, "In attesa rilevamento manovre...", 10)
        self.refresh_chapters_table()

    def update_chapters(self, video_path: str, chapters: list):
        if self.current_video_path == video_path:
            if self.current_sidecar:
                self.current_sidecar.chapters = chapters
            if chapters:
                self.set_maneuver_progress(video_path, f"{len(chapters)} manovre pronte", 100)
            else:
                self.set_maneuver_progress(video_path, "Nessuna manovra rilevata", 100)
            self.refresh_chapters_table()

    def refresh_chapters_table(self):
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

    def _on_detect_maneuvers_clicked(self):
        if not self.current_video_path:
            return
        dlg = DetectManeuversEngineDialog(parent=self)
        if dlg.exec():
            selected_model = dlg.selected_model
            self.set_maneuver_progress(self.current_video_path, f"Avvio rilevamento ({selected_model})...", 10)
            self.detect_maneuvers_requested.emit(self.current_video_path, selected_model)

    def _on_inspect_transcription_clicked(self):
        if not self.current_video_path:
            return
        dlg = TranscriptionInspectorDialog(
            video_path=self.current_video_path,
            maneuver_detector=self.maneuver_detector,
            parent=self
        )
        dlg.seek_requested.connect(self.media_player.setPosition)
        dlg.exec()

    def _on_inspect_wing_color_clicked(self):
        if not self.current_video_path:
            return
        dlg = WingColorInspectorDialog(
            video_path=self.current_video_path,
            parent=self
        )
        dlg.exec()

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
                self.refresh_chapters_table()

    def _on_back_clicked(self):
        self.media_player.pause()
        self.back_to_table_requested.emit()

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.btn_play.setText("▶ Play")
        else:
            self.media_player.play()
            self.btn_play.setText("⏸ Pausa")

    def seek(self, offset_ms: int):
        new_pos = max(0, min(self.media_player.position() + offset_ms, self.media_player.duration()))
        self.media_player.setPosition(new_pos)

    def toggle_fullscreen(self):
        if self.video_widget.isFullScreen():
            self.video_widget.setFullScreen(False)
            self.btn_fullscreen.setText("⛶ Schermo Intero (F)")
        else:
            self.video_widget.setFullScreen(True)
            self.btn_fullscreen.setText("Normale (ESC)")

    def handle_escape(self):
        if self.video_widget.isFullScreen():
            self.video_widget.setFullScreen(False)
            self.btn_fullscreen.setText("⛶ Schermo Intero (F)")
        else:
            self._on_back_clicked()

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

    def pause(self):
        self.media_player.pause()
        self.btn_play.setText("▶ Play")

    def is_fullscreen(self) -> bool:
        return self.video_widget.isFullScreen()

    def exit_fullscreen(self):
        self.video_widget.setFullScreen(False)
        self.btn_fullscreen.setText("⛶ Schermo Intero (F)")
