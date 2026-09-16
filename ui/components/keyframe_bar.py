from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal


class KeyframeBar(QFrame):
    """
    Barra di controllo compatta per la gestione dei keyframe di tracciamento:
    - Selezione soggetto attivo (🔵 Pilota / 🟠 Vela)
    - Aggiunta manuale keyframe (+ KF o tasto K)
    - Eliminazione keyframe corrente (🗑 o tasto Canc)
    - Navigazione rapida tra i keyframe (⏮ / ⏭ o Alt+Freccia)
    - Ripristino al tracciamento automatico originale
    - Badge informativo dello stato dei keyframe
    """
    add_keyframe_requested = pyqtSignal(str)
    delete_keyframe_requested = pyqtSignal(str)
    prev_keyframe_requested = pyqtSignal()
    next_keyframe_requested = pyqtSignal()
    reset_keyframes_requested = pyqtSignal()
    active_subject_changed = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._active_subject = "pilot"
        self._keyframes: Dict[str, Any] = {"pilot": [], "wing": []}
        self._init_ui()

    def _init_ui(self):
        self.setObjectName("keyframeBar")
        self.setStyleSheet("""
            QFrame#keyframeBar {
                background-color: #0b111e;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 2px 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Selettore Soggetto (Pilota / Vela)
        lbl_target = QLabel("Modifica:")
        lbl_target.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8;")
        layout.addWidget(lbl_target)

        self.btn_pilot = QPushButton("🔵 Pilota")
        self.btn_pilot.setCheckable(True)
        self.btn_pilot.setChecked(True)
        self.btn_pilot.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 700; padding: 4px 10px;
                background-color: #0c4a6e; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px;
            }
            QPushButton:checked { background-color: #0369a1; color: #ffffff; border-color: #38bdf8; }
        """)
        self.btn_pilot.clicked.connect(lambda: self.set_active_subject("pilot"))
        layout.addWidget(self.btn_pilot)

        self.btn_wing = QPushButton("🟠 Vela")
        self.btn_wing.setCheckable(True)
        self.btn_wing.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 700; padding: 4px 10px;
                background-color: #451a03; color: #fbbf24; border: 1px solid #d97706; border-radius: 6px;
            }
            QPushButton:checked { background-color: #b45309; color: #ffffff; border-color: #f59e0b; }
        """)
        self.btn_wing.clicked.connect(lambda: self.set_active_subject("wing"))
        layout.addWidget(self.btn_wing)

        layout.addSpacing(6)

        # Pulsanti Azione Keyframe
        self.btn_add = QPushButton("◆ + KF (K)")
        self.btn_add.setToolTip("Aggiunge o fissa un keyframe al secondo corrente")
        self.btn_add.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 600; padding: 4px 10px;
                background-color: #131b2e; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px;
            }
            QPushButton:hover { background-color: #1e293b; border-color: #38bdf8; }
        """)
        self.btn_add.clicked.connect(lambda: self.add_keyframe_requested.emit(self._active_subject))
        layout.addWidget(self.btn_add)

        self.btn_del = QPushButton("🗑 Canc KF")
        self.btn_del.setToolTip("Elimina il keyframe al secondo corrente")
        self.btn_del.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 600; padding: 4px 8px;
                background-color: #131b2e; color: #ef4444; border: 1px solid #334155; border-radius: 6px;
            }
            QPushButton:hover { background-color: #450a0a; border-color: #ef4444; }
        """)
        self.btn_del.clicked.connect(lambda: self.delete_keyframe_requested.emit(self._active_subject))
        layout.addWidget(self.btn_del)

        # Navigazione Keyframe
        self.btn_prev = QPushButton("⏮ KF")
        self.btn_prev.setToolTip("Salta al keyframe precedente (Alt+Sinistra)")
        self.btn_prev.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 600; padding: 4px 8px;
                background-color: #131b2e; color: #94a3b8; border: 1px solid #334155; border-radius: 6px;
            }
            QPushButton:hover { background-color: #1e293b; color: #ffffff; }
        """)
        self.btn_prev.clicked.connect(self.prev_keyframe_requested.emit)
        layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("KF ⏭")
        self.btn_next.setToolTip("Salta al keyframe successivo (Alt+Destra)")
        self.btn_next.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 600; padding: 4px 8px;
                background-color: #131b2e; color: #94a3b8; border: 1px solid #334155; border-radius: 6px;
            }
            QPushButton:hover { background-color: #1e293b; color: #ffffff; }
        """)
        self.btn_next.clicked.connect(self.next_keyframe_requested.emit)
        layout.addWidget(self.btn_next)

        layout.addStretch()

        # Badge Stato Keyframe
        self.lbl_status = QLabel("Nessun ritocco manuale")
        self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b;")
        layout.addWidget(self.lbl_status)

        # Pulsante Ripristina Originale AI
        self.btn_reset = QPushButton("🔄 Reset AI")
        self.btn_reset.setToolTip("Rimuove tutti i keyframe manuali e ripristina la traccia originale AI")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: 600; padding: 4px 8px;
                background-color: #131b2e; color: #94a3b8; border: 1px solid #23314f; border-radius: 6px;
            }
            QPushButton:hover { background-color: #1e293b; color: #f87171; border-color: #ef4444; }
        """)
        self.btn_reset.clicked.connect(self.reset_keyframes_requested.emit)
        layout.addWidget(self.btn_reset)

    @property
    def active_subject(self) -> str:
        return self._active_subject

    def set_active_subject(self, subject: str):
        if subject in ("pilot", "wing") and subject != self._active_subject:
            self._active_subject = subject
            self.btn_pilot.setChecked(subject == "pilot")
            self.btn_wing.setChecked(subject == "wing")
            self.active_subject_changed.emit(subject)
            self._update_status_label()

    def set_keyframes(self, keyframes: dict):
        self._keyframes = keyframes if isinstance(keyframes, dict) else {"pilot": [], "wing": []}
        self._update_status_label()

    def _update_status_label(self):
        p_count = len(self._keyframes.get("pilot", []))
        w_count = len(self._keyframes.get("wing", []))
        total = p_count + w_count
        if total == 0:
            self.lbl_status.setText("Tracciamento originale AI (0 KF)")
            self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b;")
        else:
            self.lbl_status.setText(f"◆ {total} Keyframe ({p_count} Pilota, {w_count} Vela)")
            self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 700; color: #38bdf8;")
