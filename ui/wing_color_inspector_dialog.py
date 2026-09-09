import os
import subprocess
from typing import List, Tuple
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QScrollArea, QWidget
)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt
from core.audio_extractor import get_ffmpeg_binary, get_video_duration
from core.wing_color_detector import (
    classify_rgb_color, extract_keyframe_colors_from_ppm,
    detect_wing_colors_from_video, COLOR_PALETTE
)

class WingColorInspectorDialog(QDialog):
    """
    Finestra diagnostica per ispezionare visivamente il rilevamento colore della vela:
    - Mostra i fotogrammi campionati dal video (keyframe)
    - Mostra la scomposizione percentuale dei colori rilevati
    - Spiega chiaramente quali porzioni sono state filtrate (cielo/lago) vs catalogate
    """
    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        fname = os.path.basename(video_path)
        self.setWindowTitle(f"🎨 Diagnostica Colori Vela - {fname}")
        self.resize(760, 520)
        self._init_ui()
        self._run_analysis()

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
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header
        top = QHBoxLayout()
        self.lbl_title = QLabel(f"<b>Analisi cromatica fotogrammi:</b> {os.path.basename(self.video_path)}")
        self.lbl_title.setStyleSheet("font-size: 15px; color: #38bdf8;")
        top.addWidget(self.lbl_title)
        top.addStretch()
        layout.addLayout(top)

        # Area Frame Campionati
        lbl_frames_title = QLabel("FOTOGRAMMI CAMPIONATI DALLA CLIP:")
        lbl_frames_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        layout.addWidget(lbl_frames_title)

        self.frames_layout = QHBoxLayout()
        self.frames_layout.setSpacing(10)
        layout.addLayout(self.frames_layout)

        # Risultato Colori
        lbl_colors_title = QLabel("COLORI DOMINANTI DELLA VELA RILEVATI:")
        lbl_colors_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px; margin-top: 8px;")
        layout.addWidget(lbl_colors_title)

        self.colors_box = QHBoxLayout()
        self.colors_box.setSpacing(12)
        layout.addLayout(self.colors_box)

        # Nota informativa
        hint = QLabel(
            "ℹ️ <b>Come funziona il rilevatore:</b> L'algoritmo campiona i fotogrammi a intervalli regolari, "
            "filtra automaticamente le sfumature di blu/ciano dell'acqua del lago e del cielo nuvoloso/aperto, "
            "isolando la pigmentazione satura dell'estradosso/intradosso della vela."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 11px; margin-top: 10px;")
        layout.addWidget(hint)

        # Bottom Bar
        b_bar = QHBoxLayout()
        b_bar.addStretch()
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        b_bar.addWidget(btn_close)
        layout.addLayout(b_bar)

    def _run_analysis(self):
        if not os.path.exists(self.video_path):
            return

        dur = get_video_duration(self.video_path)
        if dur <= 0:
            dur = 10.0

        sample_ts = [dur * 0.20, dur * 0.40, dur * 0.65]
        ffmpeg_exe = get_ffmpeg_binary()

        # Mostra i 3 fotogrammi
        for i, ts in enumerate(sample_ts):
            frame_box = QVBoxLayout()
            lbl_time = QLabel(f"T = {int(ts//60):02d}:{int(ts%60):02d}")
            lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_time.setStyleSheet("font-size: 11px; font-weight: bold; color: #cbd5e1;")
            frame_box.addWidget(lbl_time)

            img_label = QLabel()
            img_label.setFixedSize(220, 124)
            img_label.setStyleSheet("border: 1px solid #1e293b; border-radius: 6px; background-color: #000000;")
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            cmd = [
                ffmpeg_exe,
                "-ss", str(round(ts, 2)),
                "-i", str(self.video_path),
                "-vframes", "1",
                "-s", "320x180",
                "-f", "image2pipe",
                "-vcodec", "ppm",
                "-"
            ]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
                if res.returncode == 0 and res.stdout.startswith(b"P6"):
                    tokens = res.stdout[:100].split()
                    w, h = int(tokens[1]), int(tokens[2])
                    header_end = res.stdout.find(b"\n", res.stdout.find(tokens[3])) + 1
                    raw_rgb = res.stdout[header_end:]
                    qimg = QImage(raw_rgb, w, h, 3 * w, QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimg)
                    img_label.setPixmap(pixmap.scaled(220, 124, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            except Exception:
                img_label.setText("Errore estrazione")

            frame_box.addWidget(img_label)
            self.frames_layout.addLayout(frame_box)

        # Rileva e mostra badge cromatici
        detected = detect_wing_colors_from_video(self.video_path, duration=dur)
        if detected:
            for name, hex_c in detected:
                badge = QFrame()
                badge.setStyleSheet(f"""
                    QFrame {{
                        background-color: #1e293b;
                        border: 1.5px solid {hex_c};
                        border-radius: 8px;
                        padding: 6px 14px;
                    }}
                """)
                b_lay = QHBoxLayout(badge)
                b_lay.setContentsMargins(6, 4, 6, 4)
                b_lay.setSpacing(8)

                dot = QLabel()
                dot.setFixedSize(14, 14)
                dot.setStyleSheet(f"background-color: {hex_c}; border-radius: 7px;")
                b_lay.addWidget(dot)

                lbl_name = QLabel(name)
                lbl_name.setStyleSheet("font-weight: 700; color: #f8fafc; font-size: 13px;")
                b_lay.addWidget(lbl_name)

                self.colors_box.addWidget(badge)
            self.colors_box.addStretch()
        else:
            lbl_none = QLabel("Nessun colore saturo isolabile rispetto allo sfondo.")
            lbl_none.setStyleSheet("color: #94a3b8; font-style: italic;")
            self.colors_box.addWidget(lbl_none)
            self.colors_box.addStretch()
