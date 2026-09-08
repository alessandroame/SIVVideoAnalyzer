import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSlider,
    QFileDialog, QMessageBox, QTextEdit, QSplitter, QComboBox, QFrame
)
from PyQt6.QtCore import Qt, QUrl, QTime, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

class ChaptersView(QWidget):
    pilot_selected_signal = pyqtSignal(str)
    flight_selected_signal = pyqtSignal(int)
    save_changes_signal = pyqtSignal()
    back_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chapters = []
        self.current_flight = None
        self.current_video_path = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Top Bar: Selettore Pilota e Selettore Volo (Dark theme coerente)
        top_bar = QFrame()
        top_bar.setStyleSheet("""
            QFrame {
                background-color: #1e293b; 
                border-radius: 6px; 
                padding: 6px;
                border: 1px solid #334155;
            }
            QLabel {
                color: #f1f5f9;
            }
        """)
        l_top = QHBoxLayout(top_bar)

        self.btn_back = QPushButton("⬅ Torna a Revisione")
        self.btn_back.setStyleSheet("padding: 6px 14px; font-size: 13px;")
        self.btn_back.clicked.connect(self.back_signal.emit)
        l_top.addWidget(self.btn_back)

        l_top.addSpacing(15)
        lbl_pilota = QLabel("<b>Pilota:</b>")
        lbl_pilota.setStyleSheet("font-size: 13px; color: #38bdf8;")
        l_top.addWidget(lbl_pilota)

        self.combo_pilots = QComboBox()
        self.combo_pilots.setMinimumWidth(220)
        self.combo_pilots.setStyleSheet("padding: 5px; font-size: 13px; font-weight: bold;")
        self.combo_pilots.currentIndexChanged.connect(self.on_pilot_combo_changed)
        l_top.addWidget(self.combo_pilots)

        l_top.addSpacing(15)
        lbl_volo = QLabel("<b>Sessione Volo:</b>")
        lbl_volo.setStyleSheet("font-size: 13px; color: #38bdf8;")
        l_top.addWidget(lbl_volo)

        self.combo_flights = QComboBox()
        self.combo_flights.setMinimumWidth(180)
        self.combo_flights.setStyleSheet("padding: 5px; font-size: 13px; font-weight: bold;")
        self.combo_flights.currentIndexChanged.connect(self.on_flight_combo_changed)
        l_top.addWidget(self.combo_flights)

        l_top.addStretch()

        self.lbl_flight_meta = QLabel("")
        self.lbl_flight_meta.setStyleSheet("color: #94a3b8; font-style: italic; font-size: 12px;")
        l_top.addWidget(self.lbl_flight_meta)

        main_layout.addWidget(top_bar)

        # Splitter principale: Sinistra Player (75%), Destra Capitoli (25%)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sinistra: Player Video
        player_container = QWidget()
        player_layout = QVBoxLayout(player_container)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.setSpacing(6)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(640, 360)
        self.video_widget.setStyleSheet("background-color: black; border-radius: 6px;")
        player_layout.addWidget(self.video_widget, stretch=1)

        # Media Player
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        # Controlli player grandi per uso rapido
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(8)

        self.btn_play_pause = QPushButton("▶ Play")
        self.btn_play_pause.setStyleSheet("""
            QPushButton {
                font-size: 15px; 
                font-weight: bold; 
                padding: 8px 18px; 
                background-color: #0284c7; 
                color: white; 
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_play_pause.clicked.connect(self.toggle_play)
        ctrl_layout.addWidget(self.btn_play_pause)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("font-size: 14px; font-weight: bold; min-width: 110px;")
        ctrl_layout.addWidget(self.time_label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.set_position)
        ctrl_layout.addWidget(self.slider)

        player_layout.addLayout(ctrl_layout)
        splitter.addWidget(player_container)

        # Destra: Tabella Capitoli ed Esportazione
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        lbl_caps = QLabel("<b>Manovre del Volo (clicca due volte per vedere):</b>")
        lbl_caps.setStyleSheet("font-size: 13px; color: #f8fafc;")
        right_layout.addWidget(lbl_caps)

        self.table_chapters = QTableWidget(0, 3)
        self.table_chapters.setHorizontalHeaderLabels(["Minutaggio", "Manovra", "Comando Radio"])
        self.table_chapters.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_chapters.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_chapters.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_chapters.setStyleSheet("""
            QTableWidget {
                font-size: 13px;
                selection-background-color: #0284c7;
            }
        """)
        self.table_chapters.cellDoubleClicked.connect(self.on_chapter_double_clicked)
        self.table_chapters.setAlternatingRowColors(True)
        right_layout.addWidget(self.table_chapters)

        # Pulsanti gestione
        action_layout = QHBoxLayout()
        self.btn_save_changes = QPushButton("💾 Salva Modifiche")
        self.btn_save_changes.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 14px; font-size: 13px;")
        self.btn_save_changes.clicked.connect(self.save_changes_signal.emit)
        action_layout.addWidget(self.btn_save_changes)

        action_layout.addStretch()

        self.btn_export_yt = QPushButton("Esporta YouTube")
        self.btn_export_yt.setStyleSheet("padding: 6px 12px; font-size: 13px;")
        self.btn_export_yt.clicked.connect(self.export_youtube)
        action_layout.addWidget(self.btn_export_yt)

        right_layout.addLayout(action_layout)
        splitter.addWidget(right_container)

        # Proporzione 70% video, 30% lista capitoli
        splitter.setSizes([750, 320])
        main_layout.addWidget(splitter, stretch=1)

        # Segnali player
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)

    def set_pilots_list(self, pilots: list, current_pilot: str = None):
        self.combo_pilots.blockSignals(True)
        self.combo_pilots.clear()
        for p in pilots:
            if isinstance(p, tuple):
                name, display_text = p
                self.combo_pilots.addItem(display_text, name)
            else:
                self.combo_pilots.addItem(str(p), str(p))
                
        if current_pilot:
            idx = self.combo_pilots.findData(current_pilot)
            if idx >= 0:
                self.combo_pilots.setCurrentIndex(idx)
        self.combo_pilots.blockSignals(False)

    def set_flights_list(self, flights: list, current_flight_number: int = 1):
        self.combo_flights.blockSignals(True)
        self.combo_flights.clear()
        for f in flights:
            label = f"✈ Volo {f.flight_number} ({len(f.clips)} clip - {len(f.chapters)} manovre)"
            self.combo_flights.addItem(label, f.flight_number)
            
        idx = self.combo_flights.findData(current_flight_number)
        if idx >= 0:
            self.combo_flights.setCurrentIndex(idx)
        self.combo_flights.blockSignals(False)

    def on_pilot_combo_changed(self, index: int):
        pilot_id = self.combo_pilots.currentData()
        if pilot_id:
            self.pilot_selected_signal.emit(pilot_id)

    def on_flight_combo_changed(self, index: int):
        flight_num = self.combo_flights.currentData()
        if flight_num is not None:
            self.flight_selected_signal.emit(flight_num)

    def load_flight(self, flight):
        self.current_flight = flight
        self.set_chapters(flight.chapters)

        clip_names = ", ".join(c.filename for c in flight.clips)
        self.lbl_flight_meta.setText(f"Clip: {clip_names} | Totale: {int(flight.total_duration // 60):02d}:{int(flight.total_duration % 60):02d}")

        if flight.clips:
            # Carica la prima clip
            first_clip = flight.clips[0]
            self.load_video(first_clip.video_path)

    def load_video(self, video_path: str):
        self.current_video_path = video_path
        self.media_player.setSource(QUrl.fromLocalFile(video_path))
        self.btn_play_pause.setText("Play")

    def set_chapters(self, chapters):
        self.chapters = chapters
        self.table_chapters.setRowCount(len(chapters))
        for row, ch in enumerate(chapters):
            time_str = f"{ch.formatted_start} - {int(ch.end_time // 60):02d}:{int(ch.end_time % 60):02d}"
            item_time = QTableWidgetItem(time_str)
            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_name = QTableWidgetItem(ch.maneuver_name)
            item_text = QTableWidgetItem(ch.transcription_text)

            self.table_chapters.setItem(row, 0, item_time)
            self.table_chapters.setItem(row, 1, item_name)
            self.table_chapters.setItem(row, 2, item_text)

    def on_chapter_double_clicked(self, row, col):
        if row < len(self.chapters) and self.current_flight:
            target_flight_time = self.chapters[row].start_time
            clip, local_time = self.current_flight.get_clip_and_local_time(target_flight_time)
            
            if clip:
                if self.current_video_path != clip.video_path:
                    self.load_video(clip.video_path)
                    
                start_ms = int(local_time * 1000)
                self.media_player.setPosition(start_ms)
                self.media_player.play()
                self.btn_play_pause.setText("Pausa")

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.btn_play_pause.setText("Play")
        else:
            self.media_player.play()
            self.btn_play_pause.setText("Pausa")

    def position_changed(self, pos_ms):
        self.slider.setValue(pos_ms)
        self.update_time_label(pos_ms, self.media_player.duration())

    def duration_changed(self, dur_ms):
        self.slider.setRange(0, dur_ms)
        self.update_time_label(self.media_player.position(), dur_ms)

    def set_position(self, pos_ms):
        self.media_player.setPosition(pos_ms)

    def update_time_label(self, pos_ms, dur_ms):
        pos_sec = pos_ms // 1000
        dur_sec = dur_ms // 1000
        self.time_label.setText(
            f"{pos_sec // 60:02d}:{pos_sec % 60:02d} / {dur_sec // 60:02d}:{dur_sec % 60:02d}"
        )

    def add_manual_chapter(self):
        pos_sec = self.media_player.position() / 1000.0
        from core.maneuver_detector import SIVChapter
        ch = SIVChapter(
            start_time=pos_sec,
            end_time=pos_sec + 5.0,
            maneuver_id="manuale",
            maneuver_name="Nuova Manovra",
            category="Manuale",
            transcription_text="Aggiunta manualmente",
            confidence=1.0
        )
        self.chapters.append(ch)
        self.chapters.sort(key=lambda x: x.start_time)
        self.set_chapters(self.chapters)

    def remove_selected_chapter(self):
        selected_rows = sorted(set(index.row() for index in self.table_chapters.selectedIndexes()), reverse=True)
        for row in selected_rows:
            if row < len(self.chapters):
                self.chapters.pop(row)
        self.set_chapters(self.chapters)

    def export_youtube(self):
        for row in range(self.table_chapters.rowCount()):
            name_item = self.table_chapters.item(row, 2)
            if name_item and row < len(self.chapters):
                self.chapters[row].maneuver_name = name_item.text().strip()

        from core.maneuver_detector import ManeuverDetector
        detector = ManeuverDetector()
        yt_text = detector.export_youtube_format(self.chapters)

        save_path, _ = QFileDialog.getSaveFileName(self, "Salva Capitoli", "capitoli_siv.txt", "Text Files (*.txt);;All Files (*)")
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(yt_text)
            QMessageBox.information(self, "Esportazione Completata", f"Capitoli salvati in:\n{save_path}")
