import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QFrame,
    QTextEdit, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from core.pilot_detector import parse_pilots_text

class WelcomeCardWidget(QWidget):
    """Componente autonomo per la schermata iniziale di Setup / Welcome."""
    session_started = pyqtSignal(str, str, list, dict, str) # source_dir, output_dir, pilot_names, pilot_gliders, model_name
    open_maneuvers_config_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setFixedSize(680, 580)
        card.setObjectName("welcomeCard")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(36, 28, 36, 28)
        c_layout.setSpacing(10)

        title = QLabel("Sessione Video SIV")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #38bdf8; letter-spacing: -0.5px;")
        c_layout.addWidget(title)

        subtitle = QLabel("Configura la cartella sorgente, la cartella di esportazione e i piloti iscritti.")
        subtitle.setStyleSheet("color: #94a3b8; font-size: 13px; margin-bottom: 4px;")
        c_layout.addWidget(subtitle)

        # 1. Sorgente
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
        btn_browse.clicked.connect(self._browse_source)
        f_row.addWidget(self.txt_folder, stretch=1)
        f_row.addWidget(btn_browse)
        c_layout.addLayout(f_row)
        self.txt_folder.textChanged.connect(self._on_source_path_changed)

        # Badge informativo scansione cartella
        self.lbl_scan_status = QLabel("")
        self.lbl_scan_status.setStyleSheet("font-size: 11px; font-weight: 600; padding: 4px 8px; border-radius: 6px;")
        self.lbl_scan_status.setVisible(False)
        c_layout.addWidget(self.lbl_scan_status)

        # 2. Output
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
        btn_browse_out.clicked.connect(self._browse_output)
        out_row.addWidget(self.txt_output, stretch=1)
        out_row.addWidget(btn_browse_out)
        c_layout.addLayout(out_row)

        # 3. Piloti
        p_row = QHBoxLayout()
        lbl_pilots = QLabel("PILOTI E VELE DEL CORSO")
        lbl_pilots.setStyleSheet("font-size: 11px; font-weight: 700; color: #cbd5e1; letter-spacing: 0.5px;")
        p_row.addWidget(lbl_pilots)

        self.btn_import_pilots = QPushButton("📥 Importa dai Sidecar")
        self.btn_import_pilots.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #38bdf8;
                border-radius: 6px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #0369a1;
                color: #ffffff;
            }
        """)
        self.btn_import_pilots.setToolTip("Rilevati piloti già registrati nei file video. Clicca per importarli automaticamente.")
        self.btn_import_pilots.setVisible(False)
        self.btn_import_pilots.clicked.connect(self._import_discovered_pilots)
        p_row.addWidget(self.btn_import_pilots)
        p_row.addStretch()
        c_layout.addLayout(p_row)

        hint = QLabel("Formato: <i>Nome - Colore Vela</i> (es: <code>Mario Rossi - Rosso/Nero</code>)")
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        c_layout.addWidget(hint)

        self.txt_pilots = QTextEdit()
        self.txt_pilots.setPlaceholderText("Mario Rossi - Rosso/Nero\nLuca Bianchi - Blu/Bianco\nAlessandro Ame - Lime/Nero")
        self.txt_pilots.setFixedHeight(68)
        c_layout.addWidget(self.txt_pilots)

        self.lbl_pilots_preview = QLabel("👥 Inserisci i piloti (es. uno per riga o separati da virgola)")
        self.lbl_pilots_preview.setStyleSheet("""
            background-color: #0b111e;
            color: #64748b;
            border: 1px solid #1e293b;
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 500;
        """)
        self.lbl_pilots_preview.setWordWrap(True)
        c_layout.addWidget(self.lbl_pilots_preview)
        self.txt_pilots.textChanged.connect(self._update_pilots_preview)

        # 4. Modello Whisper & Config Manovre
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

        btn_config = QPushButton("⚙️ Configura Manovre & Retry")
        btn_config.setStyleSheet("""
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
        btn_config.setToolTip("Personalizza l'elenco manovre attive e le frasi di ripetizione ('fanne un'altra', 'riproviamo')")
        btn_config.clicked.connect(self.open_maneuvers_config_requested.emit)
        m_row.addWidget(btn_config)

        c_layout.addLayout(m_row)
        c_layout.addSpacing(6)

        # 5. Pulsante Avvio
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
        self.btn_launch.clicked.connect(self._on_launch_clicked)
        c_layout.addWidget(self.btn_launch)

        layout.addWidget(card)

    def _on_source_path_changed(self, text: str):
        path = text.strip()
        from core.session_scanner import scan_session_folder
        if not path or not os.path.exists(path):
            self.lbl_scan_status.setVisible(False)
            self.btn_import_pilots.setVisible(False)
            self.btn_launch.setText("🚀  APRI REGISTRO VOLI")
            return

        scan = scan_session_folder(path)
        if scan.total_videos == 0:
            self.lbl_scan_status.setText("⚠️ Nessun file video (.mp4, .mov, .mkv) trovato nella cartella.")
            self.lbl_scan_status.setStyleSheet("background-color: #3f1a24; color: #fda4af; font-size: 11px; font-weight: 600; padding: 4px 8px; border-radius: 6px;")
            self.lbl_scan_status.setVisible(True)
            self.btn_import_pilots.setVisible(False)
            self.btn_launch.setText("🚀  APRI REGISTRO VOLI")
        elif scan.is_fully_analyzed:
            self.lbl_scan_status.setText(f"🟢 Tutti i {scan.total_videos} video sono già analizzati e pronti per il Debriefing!")
            self.lbl_scan_status.setStyleSheet("background-color: #064e3b; color: #a7f3d0; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 6px;")
            self.lbl_scan_status.setVisible(True)
            self.btn_launch.setText(f"🎬  APRI DEBRIEFING ({scan.total_videos} VOLI PRONTI)")
        elif scan.has_any_analyzed:
            num_ready = len(scan.analyzed_videos)
            num_pending = len(scan.pending_videos)
            self.lbl_scan_status.setText(f"🟡 {scan.total_videos} video trovati: {num_ready} già analizzati, {num_pending} da analizzare.")
            self.lbl_scan_status.setStyleSheet("background-color: #451a03; color: #fde047; font-size: 11px; font-weight: 600; padding: 4px 8px; border-radius: 6px;")
            self.lbl_scan_status.setVisible(True)
            self.btn_launch.setText(f"⚡  APRI E ANALIZZA {num_pending} MANCANTI")
        else:
            self.lbl_scan_status.setText(f"ℹ️ {scan.total_videos} video da analizzare.")
            self.lbl_scan_status.setStyleSheet("background-color: #172554; color: #93c5fd; font-size: 11px; font-weight: 600; padding: 4px 8px; border-radius: 6px;")
            self.lbl_scan_status.setVisible(True)
            self.btn_launch.setText("🚀  APRI REGISTRO VOLI")

        # Mostra opzione per importare i piloti se ce ne sono nei sidecar
        if scan.discovered_pilots:
            self._current_discovered_pilots = scan.discovered_pilots
            existing_text = self.txt_pilots.toPlainText().strip().lower()
            new_pilots_found = any(p.lower() not in existing_text for p in scan.discovered_pilots.keys())
            self.btn_import_pilots.setVisible(new_pilots_found)
        else:
            self.btn_import_pilots.setVisible(False)

    def _import_discovered_pilots(self):
        if not hasattr(self, "_current_discovered_pilots") or not self._current_discovered_pilots:
            return
        parsed = parse_pilots_text(self.txt_pilots.toPlainText())
        existing_names = {p.lower() for p, _ in parsed}

        added = []
        for p, g in self._current_discovered_pilots.items():
            if p.lower() not in existing_names:
                if g:
                    added.append(f"{p} - {g}")
                else:
                    added.append(p)

        if added:
            current_text = self.txt_pilots.toPlainText().strip()
            if current_text:
                new_text = current_text + "\n" + "\n".join(added)
            else:
                new_text = "\n".join(added)
            self.txt_pilots.setPlainText(new_text)
        self.btn_import_pilots.setVisible(False)

    def _update_pilots_preview(self):
        raw = self.txt_pilots.toPlainText()
        parsed = parse_pilots_text(raw)
        if not parsed:
            self.lbl_pilots_preview.setText("ℹ️ Inserisci i piloti iscritti (es. uno per riga o separati da virgola: Mario Rossi - Rosso/Nero)")
            self.lbl_pilots_preview.setStyleSheet("background-color: #0b111e; color: #64748b; border: 1px solid #1e293b; border-radius: 6px; padding: 4px 8px; font-size: 11px;")
        else:
            count = len(parsed)
            items_str = " &nbsp;|&nbsp; ".join([
                f"<b style='color:#f8fafc;'>{p}</b>" + (f" <span style='color:#38bdf8;'>({g})</span>" if g else "")
                for p, g in parsed
            ])
            badge_icon = "👤" if count == 1 else "👥"
            plural = "Pilota riconosciuto" if count == 1 else "Piloti riconosciuti"
            self.lbl_pilots_preview.setText(f"{badge_icon} <b>{count} {plural}:</b> &nbsp; {items_str}")
            self.lbl_pilots_preview.setStyleSheet("background-color: #0f172a; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; padding: 4px 8px; font-size: 11px;")

    def _browse_source(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella video SIV (Sorgente)", self.txt_folder.text().strip() or "")
        if d:
            self.txt_folder.setText(d)

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella Output Video Piloti", self.txt_output.text().strip() or "")
        if d:
            self.txt_output.setText(d)

    def _on_launch_clicked(self):
        source = self.txt_folder.text().strip()
        output = self.txt_output.text().strip()
        raw_text = self.txt_pilots.toPlainText()
        
        parsed = parse_pilots_text(raw_text)
        pilot_names = [p for p, _ in parsed]
        pilot_gliders = {p.lower(): g for p, g in parsed}

        model = self.combo_model.currentData() or "small"
        self.session_started.emit(source, output, pilot_names, pilot_gliders, model)

    def load_values(self, source: str, output: str, pilots_raw: str, model: str):
        if source:
            self.txt_folder.setText(source)
            self._on_source_path_changed(source)
        if output:
            self.txt_output.setText(output)
        if pilots_raw:
            self.txt_pilots.setPlainText(pilots_raw)
        self._update_pilots_preview()
        if model:
            idx = self.combo_model.findData(model)
            if idx >= 0:
                self.combo_model.setCurrentIndex(idx)

    def get_raw_pilots_text(self) -> str:
        return self.txt_pilots.toPlainText()

    def get_source_folder(self) -> str:
        return self.txt_folder.text().strip()

    def get_output_folder(self) -> str:
        return self.txt_output.text().strip()

    def get_selected_model(self) -> str:
        return self.combo_model.currentData() or "small"
