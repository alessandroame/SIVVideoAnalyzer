import os
from typing import List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from core.pilot_detector import VideoTranscriptionCache
from core.maneuver_detector import ManeuverDetector

class TranscriptionInspectorDialog(QDialog):
    """
    Finestra di diagnostica per ispezionare esattamente cosa ha trascritto Whisper
    e capire perché una manovra è stata riconosciuta o no.
    """
    seek_requested = pyqtSignal(int)  # offset ms

    def __init__(self, video_path: str, maneuver_detector: ManeuverDetector = None, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.maneuver_detector = maneuver_detector or ManeuverDetector()
        fname = os.path.basename(video_path)
        self.setWindowTitle(f"🔍 Diagnostica Trascrizione Whisper - {fname}")
        self.resize(750, 500)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0b111e;
                color: #f8fafc;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 13px;
            }
            QTableWidget {
                background-color: #0f172a;
                color: #f8fafc;
                gridline-color: #1e293b;
                border: 1px solid #1e293b;
                border-radius: 8px;
                font-size: 13px;
            }
            QTableWidget::item:selected {
                background-color: #0284c7;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #38bdf8;
                font-weight: 700;
                padding: 6px;
                border: none;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Intestazione
        top = QHBoxLayout()
        self.lbl_info = QLabel("Caricamento trascrizione Whisper...")
        self.lbl_info.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 14px;")
        top.addWidget(self.lbl_info)
        top.addStretch()
        layout.addLayout(top)

        # Tabella segmenti
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Tempo", "Testo Trascritto da Whisper", "Analisi Manovra"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table)

        hint = QLabel("💡 <b>Doppio clic</b> su una riga per saltare a quel timestamp nel video.")
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(hint)

        # Bottom Bar
        b_bar = QHBoxLayout()
        b_bar.addStretch()
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        b_bar.addWidget(btn_close)
        layout.addLayout(b_bar)

    def _load_data(self):
        base_name = os.path.splitext(os.path.basename(self.video_path))[0]
        cache_file = os.path.join("temp", f"{base_name}_cache.json")
        cached = VideoTranscriptionCache.load(cache_file)

        if not cached or not cached.segments:
            self.lbl_info.setText("⚠️ Nessuna trascrizione salvata in cache per questo video.")
            return

        segments = cached.segments
        self.lbl_info.setText(f"Trascrizione Whisper: {len(segments)} segmenti audio rilevati")

        # Rileva manovre per mostrare cosa aggancia l'algoritmo
        chaps = self.maneuver_detector.detect_chapters(segments)
        chap_times = {round(ch.start_time, 1): ch.maneuver_name for ch in chaps}

        self.table.setRowCount(len(segments))
        for r, seg in enumerate(segments):
            start_s = int(seg.start)
            end_s = int(seg.end)
            t_str = f"{start_s//60:02d}:{start_s%60:02d} - {end_s//60:02d}:{end_s%60:02d}"

            item_t = QTableWidgetItem(t_str)
            item_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_t.setData(Qt.ItemDataRole.UserRole, int(seg.start * 1000))
            self.table.setItem(r, 0, item_t)

            item_txt = QTableWidgetItem(seg.text)
            self.table.setItem(r, 1, item_txt)

            # Controlla se una manovra corrisponde
            matched_man = ""
            for t_k, m_name in chap_times.items():
                if abs(t_k - seg.start) < 4.0:
                    matched_man = f"🎯 {m_name}"
                    break

            if not matched_man:
                # Controlla se c'è almeno qualche parola chiave
                txt_l = seg.text.lower()
                for m in self.maneuver_detector.active_maneuvers:
                    for kw in m.get("keywords", []):
                        if kw.lower() in txt_l:
                            matched_man = f"🔎 Possibile: {m['name']}"
                            break
                    if matched_man:
                        break

            item_res = QTableWidgetItem(matched_man if matched_man else "—")
            if "🎯" in matched_man:
                item_res.setForeground(Qt.GlobalColor.green)
            elif "🔎" in matched_man:
                item_res.setForeground(Qt.GlobalColor.yellow)
            else:
                item_res.setForeground(Qt.GlobalColor.gray)

            self.table.setItem(r, 2, item_res)

    def _on_cell_double_clicked(self, row: int, col: int):
        item = self.table.item(row, 0)
        if item:
            pos_ms = item.data(Qt.ItemDataRole.UserRole)
            if pos_ms is not None:
                self.seek_requested.emit(pos_ms)
