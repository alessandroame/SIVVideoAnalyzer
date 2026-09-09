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
    segment_wing_from_ppm, detect_wing_colors_from_video, COLOR_PALETTE
)

class WingColorInspectorDialog(QDialog):
    """
    Finestra diagnostica per ispezionare visivamente il rilevamento colore della vela:
    - Mostra i fotogrammi campionati dal video (keyframe)
    - Permette di isolare ed evidenziare i SOLI pixel della vela escludendo cielo e lago
    - Mostra la scomposizione percentuale dei colori rilevati
    """
    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        fname = os.path.basename(video_path)
        self.setWindowTitle(f"🎨 Diagnostica Colori & Isolamento Vela - {fname}")
        self.resize(840, 560)
        self.show_isolated_only = True
        self.frame_data = [] # conterra (orig_pixmap, isolated_pixmap, pct_str)
        self.frame_labels = []
        self.frame_subtitles = []
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
        self.lbl_title = QLabel(f"<b>Analisi cromatica & Isolamento vela:</b> {os.path.basename(self.video_path)}")
        self.lbl_title.setStyleSheet("font-size: 15px; color: #38bdf8;")
        top.addWidget(self.lbl_title)
        top.addStretch()

        self.btn_toggle_mask = QPushButton("🔍 Vista: Solo Pixel Vela")
        self.btn_toggle_mask.setStyleSheet("""
            QPushButton {
                background-color: #0891b2;
                color: white;
                border: 1px solid #06b6d4;
                font-weight: 700;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #06b6d4;
            }
        """)
        self.btn_toggle_mask.setToolTip("Alterna tra l'inquadratura originale e l'isolamento dei soli pixel della vela.")
        self.btn_toggle_mask.clicked.connect(self._toggle_view_mode)
        top.addWidget(self.btn_toggle_mask)

        layout.addLayout(top)

        # Area Frame Campionati
        lbl_frames_title = QLabel("FOTOGRAMMI CAMPIONATI DALLA CLIP:")
        lbl_frames_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        layout.addWidget(lbl_frames_title)

        self.frames_layout = QHBoxLayout()
        self.frames_layout.setSpacing(12)
        layout.addLayout(self.frames_layout)

        # Risultato Colori
        lbl_colors_title = QLabel("COLORI DOMINANTI DELLA VELA RILEVATI SUI PIXEL ISOLATI:")
        lbl_colors_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px; margin-top: 8px;")
        layout.addWidget(lbl_colors_title)

        self.colors_box = QHBoxLayout()
        self.colors_box.setSpacing(12)
        layout.addLayout(self.colors_box)

        # Nota informativa
        hint = QLabel(
            "ℹ️ <b>Isolamento Sfondo SIV:</b> L'algoritmo vettoriale converte il fotogramma in coordinate HSV e rimuove "
            "completamente i pixel del cielo (azzurro desaturo) e dello specchio d'acqua del lago (ciano/blu/verde spento), "
            "restituendo in evidenza solo i pixel autentici del tessuto della vela del parapendio."
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

    def _toggle_view_mode(self):
        self.show_isolated_only = not self.show_isolated_only
        if self.show_isolated_only:
            self.btn_toggle_mask.setText("🔍 Vista: Solo Pixel Vela")
            self.btn_toggle_mask.setStyleSheet("""
                QPushButton {
                    background-color: #0891b2;
                    color: white;
                    border: 1px solid #06b6d4;
                    font-weight: 700;
                    padding: 6px 14px;
                }
                QPushButton:hover { background-color: #06b6d4; }
            """)
        else:
            self.btn_toggle_mask.setText("🖼️ Vista: Fotogramma Originale")
            self.btn_toggle_mask.setStyleSheet("""
                QPushButton {
                    background-color: #334155;
                    color: #f1f5f9;
                    border: 1px solid #475569;
                    font-weight: 700;
                    padding: 6px 14px;
                }
                QPushButton:hover { background-color: #475569; }
            """)

        self._update_display_pixmaps()

    def _update_display_pixmaps(self):
        for i, (orig_px, iso_px, pct_str) in enumerate(self.frame_data):
            if i < len(self.frame_labels):
                px = iso_px if (self.show_isolated_only and iso_px) else orig_px
                if px:
                    self.frame_labels[i].setPixmap(
                        px.scaled(250, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    )
                if i < len(self.frame_subtitles):
                    mode_txt = "Soli Pixel Vela" if self.show_isolated_only else "Originale"
                    self.frame_subtitles[i].setText(f"{mode_txt} • {pct_str}")

    def _run_analysis(self):
        if not os.path.exists(self.video_path):
            return

        dur = get_video_duration(self.video_path)
        if dur <= 0:
            dur = 10.0

        sample_ts = [dur * 0.20, dur * 0.40, dur * 0.65]
        ffmpeg_exe = get_ffmpeg_binary()

        self.frame_data = []
        self.frame_labels = []
        self.frame_subtitles = []

        all_isolated_colors = {}

        # Mostra i 3 fotogrammi
        for i, ts in enumerate(sample_ts):
            frame_box = QVBoxLayout()
            lbl_time = QLabel(f"T = {int(ts//60):02d}:{int(ts%60):02d}")
            lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_time.setStyleSheet("font-size: 11px; font-weight: bold; color: #cbd5e1;")
            frame_box.addWidget(lbl_time)

            img_label = QLabel()
            img_label.setFixedSize(250, 140)
            img_label.setStyleSheet("border: 1px solid #1e293b; border-radius: 6px; background-color: #000000;")
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            frame_box.addWidget(img_label)
            self.frame_labels.append(img_label)

            lbl_sub = QLabel("Analisi...")
            lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_sub.setStyleSheet("font-size: 10px; color: #94a3b8;")
            frame_box.addWidget(lbl_sub)
            self.frame_subtitles.append(lbl_sub)

            self.frames_layout.addLayout(frame_box)

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
                    raw_ppm = res.stdout
                    tokens = raw_ppm[:100].split()
                    w, h = int(tokens[1]), int(tokens[2])
                    header_end = raw_ppm.find(b"\n", raw_ppm.find(tokens[3])) + 1
                    raw_rgb = raw_ppm[header_end:]

                    # Originale Pixmap
                    qimg_orig = QImage(raw_rgb, w, h, 3 * w, QImage.Format.Format_RGB888)
                    orig_pixmap = QPixmap.fromImage(qimg_orig)

                    # Isolamento Pixel Vela
                    iso_ppm, colors, wing_pixels, _, _ = segment_wing_from_ppm(raw_ppm)
                    iso_pixmap = None
                    total_pixels = w * h
                    pct_val = (wing_pixels / max(1, total_pixels)) * 100.0
                    pct_str = f"Vela: {pct_val:.1f}% ({wing_pixels} px)"

                    if iso_ppm:
                        iso_head_end = iso_ppm.find(b"\n", iso_ppm.find(tokens[3])) + 1
                        iso_rgb = iso_ppm[iso_head_end:]
                        qimg_iso = QImage(iso_rgb, w, h, 3 * w, QImage.Format.Format_RGB888)
                        iso_pixmap = QPixmap.fromImage(qimg_iso)

                    for c_name, _ in colors:
                        all_isolated_colors[c_name] = all_isolated_colors.get(c_name, 0) + 1

                    self.frame_data.append((orig_pixmap, iso_pixmap, pct_str))
                else:
                    self.frame_data.append((None, None, "Errore"))
            except Exception:
                self.frame_data.append((None, None, "Errore"))

        self._update_display_pixmaps()

        # Rileva e mostra badge cromatici aggregati
        if all_isolated_colors:
            sorted_cols = sorted(all_isolated_colors.items(), key=lambda x: x[1], reverse=True)
            for name, _ in sorted_cols[:3]:
                hex_c = COLOR_PALETTE.get(name, "#94a3b8")
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
            lbl_none = QLabel("Nessun pixel di vela isolabile chiaramente dallo sfondo.")
            lbl_none.setStyleSheet("color: #94a3b8; font-style: italic;")
            self.colors_box.addWidget(lbl_none)
            self.colors_box.addStretch()
