from typing import Optional, List
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, pyqtSignal
from ui.components.glider_badge import GliderBadgeWidget


class ProcessingStatusWidget(QWidget):
    """
    Widget compatto per la colonna unificata 'Stato Elaborazione' del Registro Voli.
    Mostra in modo chiaro e dinamico:
    - ⚪ In coda / In attesa
    - 🎙️ Identificazione pilota (con barra di avanzamento e % audio)
    - 🎯 Rilevamento comandi e manovre SIV (con barra di avanzamento e % manovre)
    - 🟢 Risultato finale con badge manovre, tooltip dettagliato dei capitoli e colori vela
    - 📍 Indicatore di completamento tracciamento
    """
    inspect_wing_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._chapters: List[dict] = []
        self._wing_colors: List[dict] = []
        self._glider_name: str = ""
        self._has_tracking: bool = False

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Etichetta di testo principale
        self.lbl_status = QLabel("⚪ In coda...")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.lbl_status)

        # Barra di progresso dinamica (nascosta quando non c'è analisi in corso)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(110)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #23314f;
                border-radius: 6px;
                text-align: center;
                background-color: #0b111e;
                color: #94a3b8;
                font-size: 9px;
                font-weight: 700;
            }
            QProgressBar::chunk {
                background-color: #06b6d4;
                border-radius: 5px;
            }
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Badge colori vela compatto e cliccabile
        self.badge_wing = GliderBadgeWidget("", [])
        self.badge_wing.clicked.connect(self.inspect_wing_requested.emit)
        self.badge_wing.setVisible(False)
        layout.addWidget(self.badge_wing)

        layout.addStretch()

    def set_waiting(self):
        """Stato iniziale: video in coda."""
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("⚪ In coda...")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.setToolTip("Video in coda per l'analisi.")

    def set_audio_progress(self, percent: int, text: str = ""):
        """Fase 1 in corso: identificazione pilota tramite audio e vela."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(percent)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #23314f;
                border-radius: 6px;
                text-align: center;
                background-color: #0b111e;
                color: #38bdf8;
                font-size: 9px;
                font-weight: 700;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 5px;
            }
        """)
        msg = text or f"🎙️ Ascolto radio... {percent}%"
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600;")
        self.setToolTip(f"Identificazione pilota in corso: {percent}%")

    def set_pilot_identified(self, pilot_name: str, confidence: float, radio_phrase: str = ""):
        """Fase 1 completata: pilota identificato, in attesa di Fase 2."""
        pct = int(confidence * 100) if confidence <= 1.0 else int(confidence)
        if pct >= 70:
            rad_tag = f"🟢 Radio {pct}%"
            col = "#10b981"
        elif pct >= 40:
            rad_tag = f"🟡 Radio {pct}%"
            col = "#f59e0b"
        elif radio_phrase:
            rad_tag = "🟡 Radio debole"
            col = "#f59e0b"
        else:
            rad_tag = "⚪ Visivo"
            col = "#94a3b8"

        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"{rad_tag} • ⏳ In attesa manovre...")
        self.lbl_status.setStyleSheet(f"color: {col}; font-size: 11px; font-weight: 600;")
        tip = f"Pilota: {pilot_name} ({pct}%)\nFrase radio: {radio_phrase or '—'}"
        self.setToolTip(tip)

    def set_maneuver_progress(self, text: str, percent: int):
        """Fase 2 in corso: rilevamento manovre SIV."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(percent)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #23314f;
                border-radius: 6px;
                text-align: center;
                background-color: #0b111e;
                color: #c084fc;
                font-size: 9px;
                font-weight: 700;
            }
            QProgressBar::chunk {
                background-color: #9333ea;
                border-radius: 5px;
            }
        """)
        msg = f"🎯 {text} ({percent}%)" if text else f"🎯 Rilevamento manovre... {percent}%"
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet("color: #c084fc; font-size: 11px; font-weight: 600;")
        self.setToolTip(f"Analisi manovre: {text} ({percent}%)")

    def set_maneuvers_result(self, count: int, chapters: list = None):
        """Fase 2 completata: mostra il conteggio manovre e popola il tooltip."""
        self.progress_bar.setVisible(False)
        self._chapters = list(chapters or [])

        trk_suffix = " • 📍 Tracciato" if self._has_tracking else ""

        if count > 0:
            self.lbl_status.setText(f"🟢 {count} manovre{trk_suffix}")
            self.lbl_status.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 700;")
        else:
            self.lbl_status.setText(f"⚪ Nessuna manovra{trk_suffix}")
            self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")

        self._update_tooltip()

    def set_tracking_status(self, has_tracking: bool):
        """Aggiorna l'indicatore di tracciamento presente."""
        self._has_tracking = has_tracking
        txt = self.lbl_status.text()
        if has_tracking and "📍" not in txt:
            self.lbl_status.setText(f"{txt} • 📍")
        elif not has_tracking and " • 📍" in txt:
            self.lbl_status.setText(txt.replace(" • 📍 Tracciato", "").replace(" • 📍", ""))

    def set_wing_data(self, glider_name: str, wing_colors: list = None):
        """Aggiorna i colori della vela rilevati o il nome del modello."""
        self._glider_name = glider_name or ""
        self._wing_colors = list(wing_colors or [])
        if self._wing_colors or self._glider_name:
            self.badge_wing.set_data(self._glider_name, self._wing_colors)
            self.badge_wing.setVisible(True)
        else:
            self.badge_wing.setVisible(False)
        self._update_tooltip()

    def _update_tooltip(self):
        tip_lines = []
        if self._chapters:
            tip_lines.append(f"🎯 <b>{len(self._chapters)} Manovre SIV Rilevate:</b>")
            for i, ch in enumerate(self._chapters, 1):
                t_start = ch.get("start", 0)
                m = int(t_start // 60)
                s = int(t_start % 60)
                title = ch.get("title", f"Manovra {i}")
                cmd = ch.get("instructor_command", "")
                cmd_txt = f" (<i>'{cmd}'</i>)" if cmd else ""
                tip_lines.append(f"• [{m:02d}:{s:02d}] <b>{title}</b>{cmd_txt}")
        else:
            tip_lines.append("⚪ Nessuna manovra rilevata")

        if self._glider_name or self._wing_colors:
            tip_lines.append("")
            w_str = f"🪂 <b>Vela:</b> {self._glider_name or 'Sconosciuta'}"
            if self._wing_colors:
                c_names = [c.get("name", "") for c in self._wing_colors if c.get("name")]
                if c_names:
                    w_str += f" ({', '.join(c_names)})"
            tip_lines.append(w_str)
            tip_lines.append("<i>Clicca sui colori per aprire la Diagnostica</i>")

        self.setToolTip("\n".join(tip_lines))
