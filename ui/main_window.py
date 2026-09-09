import sys
import os
import glob
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QStackedWidget, QMessageBox
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QKeySequence, QShortcut

from core.sidecar_manager import SidecarData
from core.audio_extractor import get_video_creation_time, get_formatted_video_datetime
from core.session_scanner import scan_session_folder
from core.transcriber import SIVTranscriber
from core.maneuver_detector import ManeuverDetector
from core.flight_grouper import VideoExporter

from ui.components import ensure_arrow_icons
from ui.styles import get_md3_stylesheet
from ui.workers import AnalysisWorker
from ui.maneuver_worker import ManeuverCalculationWorker
from ui.components.welcome_card import WelcomeCardWidget
from ui.components.flight_table import FlightTableWidget
from ui.components.debriefing_player import DebriefingPlayerWidget
from ui.maneuvers_dialog import ManeuversConfigDialog
from ui.wing_color_inspector_dialog import WingColorInspectorDialog

class MainWindow(QMainWindow):
    """
    Finestra principale dell'applicazione (Orchestratore ad alto livello).
    Gestisce il flusso a 3 fasi collegando i componenti modulari.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SIV Video Analyzer")
        self.resize(1220, 760)

        # Configura stili Material 3
        up_path, down_path = ensure_arrow_icons()
        self.setStyleSheet(get_md3_stylesheet(up_path, down_path))

        self.settings = QSettings("SIVVideoAnalyzer", "Settings")
        self.transcriber = SIVTranscriber(model_size="small")
        self.maneuver_detector = ManeuverDetector()

        self.video_files = []
        self.worker = None

        self._setup_ui()
        self._load_saved_preferences()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(18, 16, 18, 16)
        self.main_layout.setSpacing(12)

        # Stack a 3 schermate
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)

        # FASE 1: Welcome Card
        self.page_welcome = WelcomeCardWidget(self)
        self.page_welcome.session_started.connect(self._on_session_started)
        self.page_welcome.open_maneuvers_config_requested.connect(self._open_maneuvers_config)
        self.stack.addWidget(self.page_welcome)

        # FASE 2: Flight Table
        self.page_table = FlightTableWidget(self)
        self.page_table.back_to_config_requested.connect(lambda: self.stack.setCurrentIndex(0))
        self.page_table.open_debriefing_requested.connect(self._open_debriefing)
        self.page_table.export_all_requested.connect(self._export_all_flights)
        self.page_table.reset_analysis_requested.connect(self._reset_analysis_data)
        self.page_table.inspect_wing_color_requested.connect(self._inspect_wing_color)
        self.stack.addWidget(self.page_table)

        # FASE 3: Debriefing Player
        self.page_player = DebriefingPlayerWidget(maneuver_detector=self.maneuver_detector, parent=self)
        self.page_player.back_to_table_requested.connect(self._back_to_table)
        self.page_player.export_current_flight_requested.connect(self._export_current_flight)
        self.page_player.detect_maneuvers_requested.connect(self._on_detect_maneuvers_requested)
        self.stack.addWidget(self.page_player)

        # Scorciatoie globali
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._toggle_play)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self._toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._handle_escape)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._seek(-5000))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._seek(5000))

    def _load_saved_preferences(self):
        saved_f = self.settings.value("source_dir", "")
        saved_out = self.settings.value("output_dir", "")
        saved_p = self.settings.value("pilots", "")
        saved_mod = self.settings.value("whisper_model", "small")
        self.page_welcome.load_values(saved_f, saved_out, saved_p, saved_mod)

    def _save_preferences(self):
        self.settings.setValue("source_dir", self.page_welcome.get_source_folder())
        self.settings.setValue("output_dir", self.page_welcome.get_output_folder())
        self.settings.setValue("pilots", self.page_welcome.get_raw_pilots_text())
        self.settings.setValue("whisper_model", self.page_welcome.get_selected_model())
        self.settings.sync()

    def _open_maneuvers_config(self):
        dlg = ManeuversConfigDialog(self.maneuver_detector, self)
        dlg.exec()

    def _on_session_started(self, source_dir: str, output_dir: str, pilot_names: list, pilot_gliders: dict, model_name: str):
        if not source_dir or not os.path.exists(source_dir):
            QMessageBox.warning(self, "Attenzione", "Seleziona una cartella video valida.")
            return

        self._save_preferences()

        scan = scan_session_folder(source_dir)
        if scan.total_videos == 0:
            QMessageBox.warning(self, "Nessun Video", "Nessun file video (.mp4, .mov, .mkv) trovato nella cartella specificata.")
            return

        self.video_files = scan.all_videos

        ready_count = len(scan.analyzed_videos)
        pending_count = len(scan.pending_videos)
        if pending_count == 0:
            status_summary = f"Tutti i {scan.total_videos} video sono già pronti"
        elif ready_count > 0:
            status_summary = f"{ready_count} pronti, {pending_count} da analizzare"
        else:
            status_summary = f"{scan.total_videos} video da analizzare"

        title = f"<b>Sessione:</b> {os.path.basename(source_dir)} ({scan.total_videos} video - {status_summary})"
        self.page_table.set_session_info(title, pilot_names, pilot_gliders)
        self.stack.setCurrentIndex(1)
        QApplication.processEvents()

        videos_to_process = []
        for vf in self.video_files:
            sc = SidecarData(vf)
            rec_dt = sc.recorded_at
            if not rec_dt:
                rec_dt = get_formatted_video_datetime(vf)
                if rec_dt and rec_dt != "—":
                    sc.recorded_at = rec_dt
                    sc.save()

            glider_col = sc.glider or pilot_gliders.get(sc.pilot_name.lower(), "")
            if sc.pilot_name:
                calc_conf = 1.0 if sc.manual_override else (sc.confidence if sc.confidence > 0 else 0.90)
                phrase = sc.radio_phrase or ("— (Nessuna chiamata radio)" if not sc.manual_override else "Assegnato manualmente")
                self.page_table.add_flight_row(
                    vf, sc.pilot_name, sc.flight_number or 1, glider_col, phrase,
                    is_confirmed=True, confidence=calc_conf, recorded_at=rec_dt,
                    wing_colors=sc.wing_colors
                )
            else:
                self.page_table.add_flight_row(
                    vf, "In attesa...", 1, "", "In coda di analisi...",
                    is_confirmed=False, recorded_at=rec_dt,
                    wing_colors=sc.wing_colors
                )
                videos_to_process.append(vf)

        if videos_to_process:
            self.transcriber.set_model_size(model_name)
            self.page_table.update_overall_progress("Avvio analisi...", 0)
            self.worker = AnalysisWorker(
                video_files=videos_to_process,
                pilot_names=pilot_names,
                transcriber=self.transcriber,
                maneuver_detector=self.maneuver_detector,
                pilot_gliders=pilot_gliders
            )
            self.worker.clip_analyzed.connect(self.page_table.on_clip_analyzed)
            self.worker.clip_progress.connect(self.page_table.update_clip_progress)
            self.worker.overall_progress.connect(self.page_table.update_overall_progress)
            self.worker.status_update.connect(self.page_table.set_worker_status)
            self.worker.maneuvers_ready.connect(self.page_player.update_chapters)
            self.worker.maneuver_progress.connect(self.page_player.set_maneuver_progress)
            self.worker.maneuver_progress.connect(self.page_table.update_maneuver_progress)
            self.worker.start()
        else:
            self.page_table.hide_progress()
            self.page_table.set_worker_status("Tutti i video sono già stati analizzati.")

    def _reset_analysis_data(self):
        if not self.video_files:
            return

        reply = QMessageBox.question(
            self,
            "Conferma Reset Analisi",
            "Vuoi cancellare i dati di riconoscimento per questa sessione e rieseguire l'analisi da zero?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.worker.wait(1000)

        for vf in self.video_files:
            sc_path = os.path.splitext(vf)[0] + ".json"
            if os.path.exists(sc_path):
                try:
                    os.remove(sc_path)
                except Exception:
                    pass

        if os.path.exists("temp"):
            for f in glob.glob("temp/*_cache.json") + glob.glob("temp/*.wav"):
                try:
                    os.remove(f)
                except Exception:
                    pass

        self.page_welcome._on_launch_clicked()

    def _open_debriefing(self, video_path: str):
        self.page_player.open_video(video_path)
        sc = SidecarData(video_path)
        if not sc.chapters:
            if self.worker and self.worker.isRunning():
                self.worker.request_priority_video(video_path)
            else:
                self._man_worker = ManeuverCalculationWorker(
                    video_path=video_path,
                    transcriber=self.transcriber,
                    maneuver_detector=self.maneuver_detector,
                    pilot_names=self.page_table.known_pilots
                )
                self._man_worker.maneuvers_ready.connect(self.page_player.update_chapters)
                self._man_worker.maneuvers_ready.connect(lambda vp, chs: self.page_table.update_maneuver_progress(vp, f"{len(chs)} manovre", 100))
                self._man_worker.progress_update.connect(self.page_player.set_maneuver_progress)
                self._man_worker.progress_update.connect(self.page_table.update_maneuver_progress)
                self._man_worker.start()
        self.stack.setCurrentIndex(2)

    def _on_detect_maneuvers_requested(self, video_path: str, model_name: str):
        if not video_path or not os.path.exists(video_path):
            return

        self.transcriber.set_model_size(model_name)

        if hasattr(self, "_man_worker") and self._man_worker and self._man_worker.isRunning():
            self._man_worker.wait(500)

        self._man_worker = ManeuverCalculationWorker(
            video_path=video_path,
            transcriber=self.transcriber,
            maneuver_detector=self.maneuver_detector,
            pilot_names=self.page_table.known_pilots,
            force_recalculate=True
        )
        self._man_worker.maneuvers_ready.connect(self.page_player.update_chapters)
        self._man_worker.maneuvers_ready.connect(lambda vp, chs: self.page_table.update_maneuver_progress(vp, f"{len(chs)} manovre", 100))
        self._man_worker.progress_update.connect(self.page_player.set_maneuver_progress)
        self._man_worker.progress_update.connect(self.page_table.update_maneuver_progress)
        self._man_worker.start()

    def _inspect_wing_color(self, video_path: str):
        if not video_path or not os.path.exists(video_path):
            return
        dlg = WingColorInspectorDialog(video_path, parent=self)
        dlg.exec()

    def _back_to_table(self):
        self.page_player.pause()
        self.stack.setCurrentIndex(1)

    def _export_current_flight(self):
        curr_video = self.page_player.current_video_path
        if not curr_video or not os.path.exists(curr_video):
            QMessageBox.warning(self, "Attenzione", "Nessun video valido aperto per l'esportazione.")
            return

        out_dir = self.page_welcome.get_output_folder()
        if not out_dir:
            source_dir = self.page_welcome.get_source_folder()
            out_dir = os.path.join(source_dir if source_dir else os.path.dirname(curr_video), "Output_Piloti")

        sc = self.page_player.current_sidecar or SidecarData(curr_video)
        p_name = sc.pilot_name or "Pilota_Sconosciuto"
        fl_num = sc.flight_number or 1

        self.page_player.btn_export_flight.setEnabled(False)
        self.page_player.btn_export_flight.setText("⏳ Esportazione in corso...")
        QApplication.processEvents()

        try:
            target_mp4 = VideoExporter.export_flight_video(
                output_dir=out_dir,
                pilot_name=p_name,
                flight_number=fl_num,
                video_paths=[curr_video],
                chapters=sc.chapters
            )
            QMessageBox.information(
                self,
                "Esportazione Completata",
                f"Video esportato con successo!\n\nFile salvato in:\n{target_mp4}\n\nÈ stato generato anche il file dei capitoli YouTube."
            )
        except Exception as e:
            QMessageBox.critical(self, "Errore Esportazione", f"Impossibile esportare il video:\n{e}")
        finally:
            self.page_player.btn_export_flight.setEnabled(True)
            self.page_player.btn_export_flight.setText("🎬 Esporta Video Volo")

    def _export_all_flights(self):
        if self.page_table.row_count() == 0:
            QMessageBox.warning(self, "Nessun Volo", "Nessun volo presente nella sessione da esportare.")
            return

        out_dir = self.page_welcome.get_output_folder()
        if not out_dir:
            source_dir = self.page_welcome.get_source_folder()
            out_dir = os.path.join(source_dir, "Output_Piloti") if source_dir else "Output_Piloti"

        flights_map = self.page_table.get_flights_map_for_export()
        if not flights_map:
            QMessageBox.warning(self, "Attenzione", "Nessun volo ha un pilota assegnato valido da esportare.")
            return

        exported_count = 0
        errors = []
        self.page_table.set_worker_status("⏳ Esportazione video in corso...")
        QApplication.processEvents()

        for (p_name, fl_num), v_paths in flights_map.items():
            try:
                sc = SidecarData(v_paths[0])
                VideoExporter.export_flight_video(
                    output_dir=out_dir,
                    pilot_name=p_name,
                    flight_number=fl_num,
                    video_paths=v_paths,
                    chapters=sc.chapters
                )
                exported_count += 1
            except Exception as e:
                errors.append(f"{p_name} Volo {fl_num}: {e}")

        self.page_table.set_worker_status(f"Esportazione completata ({exported_count} voli)")
        if errors:
            QMessageBox.warning(
                self,
                "Esportazione Parziale",
                f"Esportati {exported_count} voli su {len(flights_map)}.\nErrori riscontrati:\n" + "\n".join(errors)
            )
        else:
            QMessageBox.information(
                self,
                "Esportazione Completata",
                f"Tutti i {exported_count} voli sono stati esportati con successo in:\n{out_dir}\n\nCon i relativi file dei capitoli YouTube!"
            )

    def _toggle_play(self):
        if self.stack.currentIndex() == 2:
            self.page_player.toggle_play()

    def _seek(self, offset_ms: int):
        if self.stack.currentIndex() == 2:
            self.page_player.seek(offset_ms)

    def _toggle_fullscreen(self):
        if self.stack.currentIndex() == 2:
            self.page_player.toggle_fullscreen()

    def _handle_escape(self):
        if self.stack.currentIndex() == 2:
            self.page_player.handle_escape()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.worker.wait(1500)
        event.accept()
