import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QSlider, QFrame, QSplitter, QProgressBar
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from core.sidecar_manager import SidecarData
from ui.add_chapter_dialog import AddChapterQuickDialog
from ui.detect_engine_dialog import DetectManeuversEngineDialog
from ui.transcription_inspector_dialog import TranscriptionInspectorDialog
from ui.wing_color_inspector_dialog import WingColorInspectorDialog
from ui.components.tracking_panel import TrackingPanelWidget
from ui.components.siv_video_widget import SIVVideoWidget
from ui.components.timeline_slider import SIVTimelineSlider
from ui.components.keyframe_bar import KeyframeBar
from ui.tracking_worker import TrackingWorker
from ui.scrub_worker import ScrubWorker


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
        self._scrub_worker = None
        self._was_playing_before_drag = False
        self._fps: float = 25.0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        self.video_widget.arrow_nav_requested.connect(self.handle_arrow_nav)
        self.video_widget.toggle_tracking_requested.connect(self.toggle_tracking)
        self.video_widget.toggle_boxes_requested.connect(self.toggle_bounding_boxes)
        self.video_widget.box_drag_started.connect(self._on_box_drag_started)
        self.video_widget.box_interactively_modified.connect(self._on_box_interactively_modified)
        self.video_widget.keyframe_committed.connect(self._on_keyframe_committed)
        self.media_player.setVideoOutput(self.video_widget.videoSink())

        # Splitter orizzontale: Video Principale + Pannello Tracciamento Vela e Pilota
        self.video_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.video_splitter.setStyleSheet("QSplitter::handle { background-color: #1e293b; width: 4px; border-radius: 2px; }")

        # Pannello dedicato al tracciamento zoomato di Vela e Pilota
        self.tracking_panel = TrackingPanelWidget()
        self.video_sink = self.video_widget.videoSink()
        self.video_widget.frame_decoded.connect(self._on_frame_decoded)

        self.video_splitter.addWidget(self.video_widget)
        self.video_splitter.addWidget(self.tracking_panel)
        self.video_splitter.setStretchFactor(0, 7)
        self.video_splitter.setStretchFactor(1, 3)
        self.video_splitter.setSizes([740, 310])

        v_layout.addWidget(self.video_splitter, stretch=1)

        # Timeline Slider a tutta larghezza con marker capitoli & manovre
        self.slider = SIVTimelineSlider()
        self.slider.seek_requested.connect(self._on_seek_requested)
        self.slider.valueChanged.connect(self._on_slider_value_changed)
        self.slider.drag_started.connect(self._on_drag_started)
        self.slider.drag_ended.connect(self._on_drag_ended)
        self.slider.keyframe_delete_requested.connect(self._on_slider_keyframe_delete_requested)
        v_layout.addWidget(self.slider)

        # Barra Keyframe per correzione interattiva del tracciamento
        self.keyframe_bar = KeyframeBar()
        self.keyframe_bar.add_keyframe_requested.connect(self._on_add_keyframe)
        self.keyframe_bar.delete_keyframe_requested.connect(self._on_delete_keyframe)
        self.keyframe_bar.prev_keyframe_requested.connect(self._on_prev_keyframe)
        self.keyframe_bar.next_keyframe_requested.connect(self._on_next_keyframe)
        self.keyframe_bar.reset_keyframes_requested.connect(self._on_reset_keyframes)
        self.keyframe_bar.active_subject_changed.connect(self._on_active_subject_changed)
        self.keyframe_bar.transition_window_changed.connect(self._on_transition_window_changed)
        self.keyframe_bar.create_window_requested.connect(self._on_create_window_requested)
        self.video_widget.active_subject_changed.connect(self.keyframe_bar.set_active_subject)
        v_layout.addWidget(self.keyframe_bar)

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

        ctrl_bar.addSpacing(6)

        self.btn_tracking = QPushButton("🎯 Tracking (T)")
        self.btn_tracking.setStyleSheet("""
            QPushButton {
                padding: 8px 14px;
                font-weight: 700;
                background-color: #0369a1;
                color: #ffffff;
                border: 1px solid #38bdf8;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #0284c7; }
        """)
        self.btn_tracking.setToolTip("Mostra/nasconde i due riquadri di tracciamento di Pilota e Vela (Scorciatoia: T)")
        self.btn_tracking.clicked.connect(self.toggle_tracking)
        ctrl_bar.addWidget(self.btn_tracking)

        self.btn_boxes = QPushButton("🔲 Riquadri ON (B)")
        self.btn_boxes.setStyleSheet("""
            QPushButton {
                padding: 8px 14px;
                font-weight: 700;
                background-color: #0f766e;
                color: #ffffff;
                border: 1px solid #2dd4bf;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #0d9488; }
        """)
        self.btn_boxes.setToolTip("Mostra/nasconde i riquadri di Pilota e Vela sul video principale (Scorciatoia: B)")
        self.btn_boxes.clicked.connect(self.toggle_bounding_boxes)
        ctrl_bar.addWidget(self.btn_boxes)

        ctrl_bar.addStretch()

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

        self.btn_calc_tracking = QPushButton("🎯 Calcola Tracciamento (PiP)")
        self.btn_calc_tracking.setStyleSheet("""
            QPushButton {
                padding: 7px;
                font-weight: 600;
                font-size: 11px;
                background-color: transparent;
                color: #38bdf8;
                border: 1px dashed #0284c7;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1e293b; color: #ffffff; border-color: #38bdf8; }
        """)
        self.btn_calc_tracking.setToolTip("Avvia la scansione e stabilizzazione automatica delle coordinate di Pilota e Vela per questa clip.")
        self.btn_calc_tracking.clicked.connect(self._on_calc_tracking_clicked)
        r_layout.addWidget(self.btn_calc_tracking)

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

    def open_video(self, video_path: str, auto_calc_tracking: bool = True):
        self.current_video_path = video_path
        self.current_sidecar = SidecarData(video_path)

        pilot = self.current_sidecar.pilot_name or "Pilota"
        fl = f" - Volo {self.current_sidecar.flight_number}" if self.current_sidecar.flight_number else ""
        self.lbl_flight_title.setText(f"{pilot}{fl} ({os.path.basename(video_path)})")

        self.tracking_panel.set_sidecar(self.current_sidecar)

        if self._scrub_worker:
            self._scrub_worker.stop()
            self._scrub_worker = None
        self._scrub_worker = ScrubWorker(video_path, parent=self)
        self._scrub_worker.frame_ready.connect(self._on_scrub_frame)
        self._scrub_worker.start()

        # Inizializza duration iniziale da OpenCV per reattività istantanea dello scrubber
        try:
            import cv2
            cap_tmp = cv2.VideoCapture(video_path)
            if cap_tmp.isOpened():
                fps = cap_tmp.get(cv2.CAP_PROP_FPS) or 25.0
                self._fps = float(fps)
                fc = cap_tmp.get(cv2.CAP_PROP_FRAME_COUNT)
                if fc and fc > 0:
                    dur_ms = int((fc / fps) * 1000)
                    self.slider.setRange(0, dur_ms)
                cap_tmp.release()
        except Exception:
            pass

        if self.current_sidecar.has_tracking():
            self.btn_calc_tracking.setText("✅ Tracciamento Pronto (Ricalcola)")
            self.btn_calc_tracking.setEnabled(True)
        else:
            self.btn_calc_tracking.setText("⏳ Calcolo Tracciamento (PiP)...")
            self.btn_calc_tracking.setEnabled(False)
            self.tracking_panel.set_status_all("Calcolo in corso...")
            if auto_calc_tracking:
                if not (hasattr(self, "tracking_worker") and self.tracking_worker and self.tracking_worker.isRunning()):
                    self._on_calc_tracking_clicked()

        self.media_player.setSource(QUrl.fromLocalFile(video_path))
        self.media_player.play()
        self.btn_play.setText("⏸ Pausa")
        if self.current_sidecar.chapters:
            self.hide_maneuver_progress()
        else:
            self.set_maneuver_progress(video_path, "In attesa rilevamento manovre...", 10)
        self.refresh_chapters_table()
        self._update_keyframes_ui()

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
            self.slider.set_chapters([])
            return
        chaps = self.current_sidecar.chapters
        self.slider.set_chapters(chaps)
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
        self.slider.setValue(start_ms)
        self.media_player.setPosition(start_ms)
        if self._scrub_worker:
            self._scrub_worker.request_frame(start_ms)
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
        if self._scrub_worker:
            self._scrub_worker.stop()
            self._scrub_worker = None
        self.media_player.pause()
        self.back_to_table_requested.emit()

    def _on_drag_started(self):
        self.video_widget.set_scrubbing(True)
        self._was_playing_before_drag = (self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        if self._was_playing_before_drag:
            self.media_player.pause()

    def _on_drag_ended(self):
        self.video_widget.set_scrubbing(False)
        final_pos = self.slider.value()
        self.media_player.setPosition(final_pos)
        if self._scrub_worker:
            self._scrub_worker.request_frame(final_pos)
        if self._was_playing_before_drag:
            self.media_player.play()
            self.btn_play.setText("⏸ Pausa")

    def _on_seek_requested(self, pos_ms: int):
        self.media_player.setPosition(pos_ms)
        if self._scrub_worker:
            self._scrub_worker.request_frame(pos_ms)

    def _on_scrub_frame(self, qimg, curr_s: float):
        # Mostra immediatamente il frame sul video widget principale
        self.video_widget.display_image(qimg)

        # Aggiorna i riquadri di tracking sul video principale
        if self.current_sidecar and self.current_sidecar.has_tracking():
            p_box, w_box = self.current_sidecar.get_tracking_boxes_at(curr_s)
            self.video_widget.set_bounding_boxes(p_box, w_box, force_repaint=True)
        else:
            self.video_widget.set_bounding_boxes(None, None, force_repaint=True)

        # Aggiorna le due viste PiP di Vela e Pilota con frame deinterlacciato
        if self.current_sidecar and self.tracking_panel.isVisible():
            frame_to_use = self.video_widget._current_frame or qimg
            self.tracking_panel.handle_qimage_frame(frame_to_use, curr_s, force=True)

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.btn_play.setText("▶ Play")
        else:
            self.media_player.play()
            self.btn_play.setText("⏸ Pausa")

    def seek(self, offset_ms: int):
        dur = self.media_player.duration()
        target = self.media_player.position() + offset_ms
        if dur > 0:
            target = min(target, dur)
        new_pos = max(0, target)
        self.slider.setValue(new_pos)
        self.media_player.setPosition(new_pos)
        if self._scrub_worker:
            self._scrub_worker.request_frame(new_pos)

    def handle_arrow_nav(self, direction: int):
        """
        Gestisce i tasti freccia sinistra (-1) e destra (+1):
        - In PLAY: sposta di 5 secondi (+/- 5000 ms).
        - In PAUSA: muove di esattamente 1 fotogramma (calcolato dagli fps effettivi del video).
        """
        is_playing = (self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        if is_playing:
            self.seek(direction * 5000)
        else:
            self.step_frame(direction)

    def step_frame(self, direction: int):
        """Avanza o retrocede di esattamente 1 singolo fotogramma."""
        fps = getattr(self, "_fps", 25.0) or 25.0
        cur_ms = self.media_player.position()
        current_frame = int(round((cur_ms / 1000.0) * fps))
        target_frame = max(0, current_frame + direction)
        new_pos = int(round((target_frame / fps) * 1000.0))
        dur = self.media_player.duration()
        if dur > 0:
            new_pos = min(new_pos, dur)
        self.slider.setValue(new_pos)
        self.media_player.setPosition(new_pos)
        if self._scrub_worker:
            self._scrub_worker.request_frame(new_pos)

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
        if not self.slider.is_dragging:
            self.slider.setValue(pos_ms)
            pos_s = pos_ms // 1000
            dur_s = self.media_player.duration() // 1000
            self.lbl_time.setText(f"{pos_s//60:02d}:{pos_s%60:02d} / {dur_s//60:02d}:{dur_s%60:02d}")

    def _on_slider_value_changed(self, pos_ms: int):
        pos_s = pos_ms // 1000
        dur_s = self.media_player.duration() // 1000
        self.lbl_time.setText(f"{pos_s//60:02d}:{pos_s%60:02d} / {dur_s//60:02d}:{dur_s%60:02d}")
        if self.slider.is_dragging and self._scrub_worker:
            self._scrub_worker.request_frame(pos_ms)

    def pause(self):
        self.media_player.pause()
        self.btn_play.setText("▶ Play")

    def is_fullscreen(self) -> bool:
        return self.video_widget.isFullScreen()

    def exit_fullscreen(self):
        self.video_widget.setFullScreen(False)
        self.btn_fullscreen.setText("⛶ Schermo Intero (F)")

    def toggle_tracking(self):
        new_vis = not self.tracking_panel.isVisible()
        self.tracking_panel.setVisible(new_vis)
        if new_vis:
            self.btn_tracking.setText("🎯 Tracking ON (T)")
            self.btn_tracking.setStyleSheet("""
                QPushButton {
                    padding: 8px 14px;
                    font-weight: 700;
                    background-color: #0369a1;
                    color: #ffffff;
                    border: 1px solid #38bdf8;
                    border-radius: 8px;
                }
                QPushButton:hover { background-color: #0284c7; }
            """)
        else:
            self.btn_tracking.setText("🎯 Tracking OFF (T)")
            self.btn_tracking.setStyleSheet("""
                QPushButton {
                    padding: 8px 14px;
                    font-weight: 600;
                    background-color: #131b2e;
                    color: #94a3b8;
                    border: 1px solid #23314f;
                    border-radius: 8px;
                }
                QPushButton:hover { background-color: #1c263d; border-color: #38bdf8; }
            """)

    def toggle_bounding_boxes(self):
        new_state = self.video_widget.toggle_bounding_boxes()
        if new_state:
            self.btn_boxes.setText("🔲 Riquadri ON (B)")
            self.btn_boxes.setStyleSheet("""
                QPushButton {
                    padding: 8px 14px;
                    font-weight: 700;
                    background-color: #0f766e;
                    color: #ffffff;
                    border: 1px solid #2dd4bf;
                    border-radius: 8px;
                }
                QPushButton:hover { background-color: #0d9488; }
            """)
        else:
            self.btn_boxes.setText("🔲 Riquadri OFF (B)")
            self.btn_boxes.setStyleSheet("""
                QPushButton {
                    padding: 8px 14px;
                    font-weight: 600;
                    background-color: #131b2e;
                    color: #94a3b8;
                    border: 1px solid #23314f;
                    border-radius: 8px;
                }
                QPushButton:hover { background-color: #1c263d; border-color: #38bdf8; }
            """)

    def _on_frame_decoded(self, qimg: QImage):
        if self.slider.is_dragging:
            return

        curr_s = self.media_player.position() / 1000.0

        # Aggiorna i riquadri di Pilota e Vela sul video principale (senza repaint ridondante)
        if self.current_sidecar and self.current_sidecar.has_tracking():
            p_box, w_box = self.current_sidecar.get_tracking_boxes_at(curr_s)
            self.video_widget.set_bounding_boxes(p_box, w_box, force_repaint=False)
        else:
            self.video_widget.set_bounding_boxes(None, None, force_repaint=False)

        # Aggiorna i due visualizzatori PiP se il pannello laterale è visibile (throttled a ~25 fps)
        if self.current_sidecar and self.tracking_panel.isVisible():
            self.tracking_panel.handle_qimage_frame(qimg, curr_s, force=False)

    def _on_video_frame(self, frame):
        """Metodo di compatibilità: riceve QVideoFrame e inoltra a _on_frame_decoded."""
        if not frame.isValid():
            return
        self._on_frame_decoded(frame.toImage())

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        if modifiers & Qt.KeyboardModifier.AltModifier:
            if key == Qt.Key.Key_Left:
                self._on_prev_keyframe()
                event.accept()
                return
            elif key == Qt.Key.Key_Right:
                self._on_next_keyframe()
                event.accept()
                return

        if key == Qt.Key.Key_B:
            self.toggle_bounding_boxes()
            event.accept()
        elif key == Qt.Key.Key_T:
            self.toggle_tracking()
            event.accept()
        elif key == Qt.Key.Key_K:
            self._on_add_keyframe(self.keyframe_bar.active_subject)
            event.accept()
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._on_delete_keyframe(self.keyframe_bar.active_subject)
            event.accept()
        elif key == Qt.Key.Key_Space:
            self.toggle_play()
            event.accept()
        elif key == Qt.Key.Key_Left:
            self.handle_arrow_nav(-1)
            event.accept()
        elif key == Qt.Key.Key_Right:
            self.handle_arrow_nav(1)
            event.accept()
        else:
            super().keyPressEvent(event)

    def _on_box_drag_started(self):
        """Pausa automatica del playback quando l'utente inizia a trascinare un box di tracking."""
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()

    def _on_box_interactively_modified(self, subject: str, box: list):
        """Aggiorna in tempo reale il PiP zoomato mentre l'utente trascina il box sul video."""
        curr_s = self.media_player.position() / 1000.0
        frame = self.video_widget._current_frame
        if frame and self.tracking_panel.isVisible():
            self.tracking_panel.handle_qimage_frame(frame, curr_s, force=True, override_boxes={subject: box})

    def _on_keyframe_committed(self, subject: str, box: list):
        """Salva il keyframe creato dal rilascio del mouse, ricalcola e aggiorna la timeline."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            return
        curr_s = self.media_player.position() / 1000.0
        self.current_sidecar.add_tracking_keyframe(
            subject, curr_s, box, window=self.keyframe_bar.transition_window
        )
        self._update_keyframes_ui()

    def _on_add_keyframe(self, subject: str):
        """Aggiunge o blocca un keyframe al timestamp corrente."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            return
        curr_s = self.media_player.position() / 1000.0
        p_box, w_box = self.current_sidecar.get_tracking_boxes_at(curr_s)
        box = p_box if subject == "pilot" else w_box
        if box:
            self.current_sidecar.add_tracking_keyframe(
                subject, curr_s, box, window=self.keyframe_bar.transition_window
            )
            self._update_keyframes_ui()

    def _on_delete_keyframe(self, subject: str):
        """Rimuove il keyframe al timestamp corrente."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            return
        curr_s = self.media_player.position() / 1000.0
        removed = self.current_sidecar.remove_tracking_keyframe(subject, curr_s)
        if not removed:
            other = "wing" if subject == "pilot" else "pilot"
            self.current_sidecar.remove_tracking_keyframe(other, curr_s)
        self._update_keyframes_ui()

    def _on_slider_keyframe_delete_requested(self, subject: str, t_sec: float):
        """Eliminazione diretta di un keyframe tramite clic con il tasto destro sul diamante della timeline."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            return
        removed = self.current_sidecar.remove_tracking_keyframe(subject, t_sec, tolerance=0.35)
        if not removed:
            other = "wing" if subject == "pilot" else "pilot"
            self.current_sidecar.remove_tracking_keyframe(other, t_sec, tolerance=0.35)
        self._update_keyframes_ui()

    def _on_prev_keyframe(self):
        """Salta al keyframe precedente rispetto alla posizione corrente."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            return
        curr_s = self.media_player.position() / 1000.0
        kfs = self.current_sidecar.get_tracking_keyframes()
        all_times = sorted({kf["t"] for s in ("pilot", "wing") for kf in kfs.get(s, [])})
        prev_times = [t for t in all_times if t < curr_s - 0.08]
        if prev_times:
            self._on_seek_requested(int(prev_times[-1] * 1000))

    def _on_next_keyframe(self):
        """Salta al keyframe successivo rispetto alla posizione corrente."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            return
        curr_s = self.media_player.position() / 1000.0
        kfs = self.current_sidecar.get_tracking_keyframes()
        all_times = sorted({kf["t"] for s in ("pilot", "wing") for kf in kfs.get(s, [])})
        next_times = [t for t in all_times if t > curr_s + 0.08]
        if next_times:
            self._on_seek_requested(int(next_times[0] * 1000))

    def _on_reset_keyframes(self):
        """Ripristina la traccia originale AI."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            return
        self.current_sidecar.reset_tracking_keyframes()
        self._update_keyframes_ui()

    def _on_active_subject_changed(self, subject: str):
        self.video_widget._active_target = subject

    def _on_transition_window_changed(self, window: float):
        """Aggiorna la finestra globale di transizione e ricalcola il tracciamento."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            return
        self.current_sidecar.set_tracking_transition_window(window)
        self._update_keyframes_ui()

    def _on_create_window_requested(self, subject: str, window: float):
        """Fissa una finestra di correzione al secondo corrente con l'ampiezza impostata."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            return
        curr_s = self.media_player.position() / 1000.0
        p_box, w_box = self.current_sidecar.get_tracking_boxes_at(curr_s)
        box = p_box if subject == "pilot" else w_box
        if box:
            self.current_sidecar.add_tracking_keyframe(subject, curr_s, box, window=window)
            self._update_keyframes_ui()

    def _update_keyframes_ui(self):
        """Sincronizza lo stato dei keyframe sulla barra, slider e riquadri."""
        if not self.current_sidecar or not self.current_sidecar.has_tracking():
            kfs = {"pilot": [], "wing": []}
            intervals = {"pilot": [], "wing": []}
            win = self.keyframe_bar.transition_window
        else:
            kfs = self.current_sidecar.get_tracking_keyframes()
            intervals = self.current_sidecar.get_correction_intervals()
            win = self.current_sidecar.get_tracking_transition_window()

        self.keyframe_bar.set_keyframes(kfs)
        self.keyframe_bar.set_transition_window(win)
        self.slider.set_keyframes(kfs)
        self.slider.set_correction_intervals(intervals)

        curr_s = self.media_player.position() / 1000.0
        if self.current_sidecar and self.current_sidecar.has_tracking():
            p_box, w_box = self.current_sidecar.get_tracking_boxes_at(curr_s)
            self.video_widget.set_bounding_boxes(p_box, w_box, force_repaint=True)
            if self.tracking_panel.isVisible() and self.video_widget._current_frame:
                self.tracking_panel.handle_qimage_frame(self.video_widget._current_frame, curr_s, force=True)

    def update_tracking(self, video_path: str, tracking_dict: dict):
        """Riceve l'esito del tracciamento calcolato in background."""
        if self.current_video_path == video_path:
            self._on_tracking_finished(video_path, tracking_dict)

    def set_tracking_progress(self, video_path: str, status_text: str, percent: int):
        """Riceve l'avanzamento del tracciamento calcolato in background."""
        if self.current_video_path == video_path:
            self.set_maneuver_progress(video_path, status_text, percent)

    def _on_calc_tracking_clicked(self):
        if not self.current_video_path:
            return
        if hasattr(self, "tracking_worker") and self.tracking_worker and self.tracking_worker.isRunning():
            return
        self.set_maneuver_progress(self.current_video_path, "Calcolo tracciamento Pilota & Vela in corso...", 15)
        self.btn_calc_tracking.setEnabled(False)
        self.btn_calc_tracking.setText("⏳ Calcolo Tracciamento (PiP)...")

        self.tracking_worker = TrackingWorker(self.current_video_path, parent=self)
        self.tracking_worker.progress.connect(
            lambda pct, msg: self.set_maneuver_progress(self.current_video_path, msg, pct)
        )
        self.tracking_worker.finished.connect(self._on_tracking_finished)
        self.tracking_worker.error.connect(self._on_tracking_error)
        self.tracking_worker.start()

    def _on_tracking_finished(self, video_path: str, tracking_dict: dict):
        self.btn_calc_tracking.setEnabled(True)
        if self.current_video_path == video_path:
            self.current_sidecar = SidecarData(video_path)
            self.tracking_panel.set_sidecar(self.current_sidecar)
            self.btn_calc_tracking.setText("✅ Tracciamento Pronto (Ricalcola)")
            self.set_maneuver_progress(video_path, "Tracciamento Pilota & Vela completato!", 100)
            self._update_keyframes_ui()

    def _on_tracking_error(self, video_path: str, err_msg: str):
        self.btn_calc_tracking.setEnabled(True)
        if self.current_video_path == video_path:
            self.tracking_panel.set_status_all(f"Errore: {err_msg}")
            self.set_maneuver_progress(video_path, f"Errore tracciamento: {err_msg}", 100)


