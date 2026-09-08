import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSlider,
    QFileDialog, QMessageBox, QTextEdit, QSplitter
)
from PyQt6.QtCore import Qt, QUrl, QTime
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

class ChaptersView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.chapters = []
        self.current_video_path = None
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sinistra: Player Video
        player_container = QWidget()
        player_layout = QVBoxLayout(player_container)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(480, 270)
        player_layout.addWidget(self.video_widget)

        # Media Player
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        # Controlli player
        ctrl_layout = QHBoxLayout()
        self.btn_play_pause = QPushButton("Play")
        self.btn_play_pause.clicked.connect(self.toggle_play)
        ctrl_layout.addWidget(self.btn_play_pause)

        self.time_label = QLabel("00:00 / 00:00")
        ctrl_layout.addWidget(self.time_label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.set_position)
        ctrl_layout.addWidget(self.slider)

        player_layout.addLayout(ctrl_layout)
        splitter.addWidget(player_container)

        # Destra: Tabella Capitoli ed Esportazione
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)

        right_layout.addWidget(QLabel("<b>Capitoli Manovre SIV Rilevate</b>"))

        self.table_chapters = QTableWidget(0, 4)
        self.table_chapters.setHorizontalHeaderLabels(["Inizio", "Fine", "Manovra", "Frase Radio / Trascrizione"])
        self.table_chapters.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_chapters.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_chapters.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_chapters.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_chapters.cellDoubleClicked.connect(self.on_chapter_double_clicked)
        right_layout.addWidget(self.table_chapters)

        # Pulsanti gestione ed export
        action_layout = QHBoxLayout()
        self.btn_add_chapter = QPushButton("+ Aggiungi")
        self.btn_add_chapter.clicked.connect(self.add_manual_chapter)
        action_layout.addWidget(self.btn_add_chapter)

        self.btn_remove_chapter = QPushButton("- Rimuovi")
        self.btn_remove_chapter.clicked.connect(self.remove_selected_chapter)
        action_layout.addWidget(self.btn_remove_chapter)

        action_layout.addStretch()

        self.btn_export_yt = QPushButton("Esporta YouTube / TXT")
        self.btn_export_yt.setStyleSheet("background-color: #1976d2; color: white; font-weight: bold;")
        self.btn_export_yt.clicked.connect(self.export_youtube)
        action_layout.addWidget(self.btn_export_yt)

        right_layout.addLayout(action_layout)

        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        main_layout.addWidget(splitter)

        # Timer & segnali player
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)

    def load_video(self, video_path: str):
        self.current_video_path = video_path
        self.media_player.setSource(QUrl.fromLocalFile(video_path))
        self.btn_play_pause.setText("Play")

    def set_chapters(self, chapters):
        self.chapters = chapters
        self.table_chapters.setRowCount(len(chapters))
        for row, ch in enumerate(chapters):
            item_start = QTableWidgetItem(ch.formatted_start)
            item_end = QTableWidgetItem(f"{int(ch.end_time // 60):02d}:{int(ch.end_time % 60):02d}")
            item_name = QTableWidgetItem(ch.maneuver_name)
            item_text = QTableWidgetItem(ch.transcription_text)

            self.table_chapters.setItem(row, 0, item_start)
            self.table_chapters.setItem(row, 1, item_end)
            self.table_chapters.setItem(row, 2, item_name)
            self.table_chapters.setItem(row, 3, item_text)

    def on_chapter_double_clicked(self, row, col):
        if row < len(self.chapters):
            start_ms = int(self.chapters[row].start_time * 1000)
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
        # Sincronizza modifiche dalla tabella
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
