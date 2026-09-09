import os
import time
from PyQt6.QtCore import QThread, pyqtSignal

from core.sidecar_manager import SidecarData
from core.pilot_detector import PilotDetector, VideoPilotMatch, VideoTranscriptionCache
from core.maneuver_detector import ManeuverDetector
from core.wing_color_detector import detect_wing_colors_from_video, match_detected_colors_to_pilots

class AnalysisWorker(QThread):
    clip_analyzed = pyqtSignal(object)              # emette VideoPilotMatch appena pronto
    clip_progress = pyqtSignal(str, float, float)   # video_path, sec_fatti, sec_totali
    overall_progress = pyqtSignal(str, int)         # eta_text, percent_globale
    status_update = pyqtSignal(str)
    maneuvers_ready = pyqtSignal(str, list)         # video_path, list of chapters
    maneuver_progress = pyqtSignal(str, str, int)   # video_path, status_text, percent

    def __init__(self, video_files, pilot_names, transcriber, priority_video=None, maneuver_detector=None, pilot_gliders=None):
        super().__init__()
        self.video_files = list(video_files)
        self.pilot_names = pilot_names
        self.pilot_gliders = pilot_gliders or {}
        self.transcriber = transcriber
        self.priority_video = priority_video
        self.maneuver_detector = maneuver_detector or ManeuverDetector()
        self._is_cancelled = False
        self._requested_priority = None

    def request_priority_video(self, video_path: str):
        """Richiesta dinamica: se l'istruttore apre un video, passa subito a calcolare le manovre di quello."""
        self._requested_priority = video_path

    def request_cancel(self):
        self._is_cancelled = True

    def _process_maneuvers_for_video(self, video_path: str, detector: PilotDetector, man_detector: ManeuverDetector):
        """Estrae e calcola immediatamente i capitoli/manovre per il video specifico."""
        try:
            sc = SidecarData(video_path)
            if sc.chapters:
                self.maneuver_progress.emit(video_path, f"{len(sc.chapters)} manovre caricate", 100)
                self.maneuvers_ready.emit(video_path, sc.chapters)
                return

            self.maneuver_progress.emit(video_path, "Verifica cache trascrizione...", 20)
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            cache_file = os.path.join("temp", f"{base_name}_cache.json")
            cached = VideoTranscriptionCache.load(cache_file)
            segments = []
            if cached and cached.segments:
                segments = cached.segments
                self.maneuver_progress.emit(video_path, "Trascrizione trovata in cache", 40)
            else:
                self.maneuver_progress.emit(video_path, "Ascolto radio istruttore (Whisper)...", 30)
                m = detector.identify_pilot_from_audio(video_path)
                segments = getattr(m, "segments", [])

            self.maneuver_progress.emit(video_path, "Analisi parole chiave manovre...", 70)
            if segments:
                detected_chaps = man_detector.detect_chapters(segments)
                ch_dicts = []
                for ch in detected_chaps:
                    ch_dicts.append({
                        "title": ch.maneuver_name,
                        "start": round(ch.start_time, 2),
                        "end": round(ch.end_time, 2),
                        "instructor_command": ch.transcription_text,
                        "notes": ch.category
                    })
                sc.chapters = ch_dicts
                sc.save()
                self.maneuver_progress.emit(video_path, f"{len(ch_dicts)} manovre rilevate", 100)
                self.maneuvers_ready.emit(video_path, ch_dicts)
            else:
                self.maneuver_progress.emit(video_path, "Nessun comando radio rilevato", 100)
                self.maneuvers_ready.emit(video_path, [])
        except Exception as e:
            print(f"[Worker] Errore calcolo manovre su {video_path}: {e}")
            self.maneuver_progress.emit(video_path, "Errore analisi manovre", 100)

    def run(self):
        detector = PilotDetector(pilots_list=self.pilot_names, transcriber=self.transcriber)
        man_detector = self.maneuver_detector

        # PRIORITÀ 1: Se c'è un video prioritario specificato all'avvio, fai subito le manovre
        if self.priority_video:
            self.status_update.emit(f"⚡ Rilevamento immediato manovre: {os.path.basename(self.priority_video)}...")
            self._process_maneuvers_for_video(self.priority_video, detector, man_detector)

        total_clips = len(self.video_files)
        start_time = time.time()
        clips_done = 0

        # PRIORITÀ 2: Riconoscimento nomi & radio su tutte le clip
        for i, vf in enumerate(self.video_files):
            if self._is_cancelled:
                return

            if self._requested_priority:
                p_vid = self._requested_priority
                self._requested_priority = None
                self._process_maneuvers_for_video(p_vid, detector, man_detector)

            fname = os.path.basename(vf)
            sc = SidecarData(vf)

            if sc.pilot_name:
                calc_conf = 1.0 if sc.manual_override else (sc.confidence if sc.confidence > 0 else 0.90)
                phr_list = [sc.radio_phrase] if sc.radio_phrase else []
                m = VideoPilotMatch(
                    video_path=vf,
                    filename=fname,
                    detected_pilot=sc.pilot_name,
                    confidence=calc_conf,
                    matched_phrases=phr_list,
                    duration=0.0,
                    flight_number=sc.flight_number,
                    wing_colors=sc.wing_colors
                )
                self.clip_analyzed.emit(m)
                self.clip_progress.emit(vf, 100.0, 100.0)
                clips_done += 1
                continue

            self.status_update.emit(f"Ascolto radio: {fname} ({i+1}/{total_clips})...")

            def on_file_prog(curr_s, dur_s):
                if not self._is_cancelled:
                    self.clip_progress.emit(vf, curr_s, dur_s)

            try:
                m = detector.identify_pilot_from_audio(
                    vf,
                    progress_callback=on_file_prog,
                    is_cancelled_callback=lambda: self._is_cancelled
                )
                if self._is_cancelled:
                    return

                # Rilevamento cromatico vela (Wing Color Detector)
                detected_cols = detect_wing_colors_from_video(vf, duration=m.duration)
                if detected_cols:
                    sc.wing_colors = [{"name": c[0], "hex": c[1]} for c in detected_cols]
                    m.wing_colors = sc.wing_colors

                # Fallback cromatico se il pilota non è stato rilevato via radio
                if (not m.detected_pilot or m.detected_pilot in ["In attesa...", "Da Assegnare"]) and detected_cols and self.pilot_gliders:
                    color_match = match_detected_colors_to_pilots(detected_cols, self.pilot_gliders)
                    if color_match:
                        matched_pilot_key, col_conf = color_match
                        # Trova il nome con casing originale
                        for orig_p in self.pilot_names:
                            if orig_p.lower() == matched_pilot_key.lower():
                                m.detected_pilot = orig_p
                                m.confidence = col_conf
                                m.matched_phrases.append(f"Matching Visivo Colore Vela: {', '.join([c[0] for c in detected_cols])}")
                                break

                sc.pilot_name = m.detected_pilot
                sc.flight_number = m.flight_number or 1
                sc.confidence = m.confidence
                if m.matched_phrases:
                    sc.radio_phrase = " | ".join(m.matched_phrases)
                sc.save()

                self.clip_analyzed.emit(m)
                self.clip_progress.emit(vf, 100.0, 100.0)

                if hasattr(m, "segments") and m.segments:
                    self.maneuver_progress.emit(vf, "Analisi parole chiave manovre...", 70)
                    chaps = man_detector.detect_chapters(m.segments)
                    if chaps:
                        sc.chapters = [{
                            "title": ch.maneuver_name,
                            "start": round(ch.start_time, 2),
                            "end": round(ch.end_time, 2),
                            "instructor_command": ch.transcription_text,
                            "notes": ch.category
                        } for ch in chaps]
                        sc.save()
                        self.maneuver_progress.emit(vf, f"{len(chaps)} manovre rilevate", 100)
                        self.maneuvers_ready.emit(vf, sc.chapters)
                    else:
                        self.maneuver_progress.emit(vf, "Nessuna manovra rilevata", 100)
                        self.maneuvers_ready.emit(vf, [])

            except Exception as e:
                print(f"[Worker] Errore su {fname}: {e}")

            clips_done += 1
            elapsed = time.time() - start_time
            avg_per_clip = elapsed / max(1, clips_done)
            remaining_clips = total_clips - clips_done
            est_remaining_sec = int(avg_per_clip * remaining_clips)
            est_total_sec = int(avg_per_clip * total_clips)

            pct = int((clips_done / total_clips) * 100)
            if remaining_clips > 0:
                m_rem = est_remaining_sec // 60
                s_rem = est_remaining_sec % 60
                m_tot = est_total_sec // 60
                s_tot = est_total_sec % 60
                eta_str = f"⏱ Tempo stimato: {m_rem:02d}m {s_rem:02d}s rimanenti / ~{m_tot:02d}m {s_tot:02d}s totale previsto ({clips_done}/{total_clips} clip)"
            else:
                m_el = int(elapsed) // 60
                s_el = int(elapsed) % 60
                eta_str = f"✅ Analisi completata in {m_el:02d}m {s_el:02d}s ({total_clips} clip)"

            self.overall_progress.emit(eta_str, pct)

        # PRIORITÀ 3: Perfeziona manovre su tutte le clip se non ancora calcolate
        for vf in self.video_files:
            if self._is_cancelled:
                return
            sc = SidecarData(vf)
            if not sc.chapters:
                self._process_maneuvers_for_video(vf, detector, man_detector)

        self.status_update.emit("Analisi completata.")
