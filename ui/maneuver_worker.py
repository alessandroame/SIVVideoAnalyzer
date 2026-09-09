import os
from PyQt6.QtCore import QThread, pyqtSignal
from core.sidecar_manager import SidecarData
from core.pilot_detector import PilotDetector, VideoTranscriptionCache
from core.maneuver_detector import ManeuverDetector

class ManeuverCalculationWorker(QThread):
    maneuvers_ready = pyqtSignal(str, list)
    progress_update = pyqtSignal(str, str, int)  # video_path, status_text, percent

    def __init__(self, video_path: str, transcriber, maneuver_detector, pilot_names=None, force_recalculate: bool = False):
        super().__init__()
        self.video_path = video_path
        self.transcriber = transcriber
        self.maneuver_detector = maneuver_detector or ManeuverDetector()
        self.pilot_names = pilot_names or []
        self.force_recalculate = force_recalculate

    def run(self):
        try:
            sc = SidecarData(self.video_path)
            if sc.chapters and not self.force_recalculate:
                self.progress_update.emit(self.video_path, f"{len(sc.chapters)} manovre caricate", 100)
                self.maneuvers_ready.emit(self.video_path, sc.chapters)
                return

            self.progress_update.emit(self.video_path, "Verifica cache trascrizione...", 15)
            base_name = os.path.splitext(os.path.basename(self.video_path))[0]
            cache_file = os.path.join("temp", f"{base_name}_cache.json")
            segments = []

            # Se forziamo il ricalcolo con un nuovo modello, bypassiamo la vecchia cache
            if not self.force_recalculate:
                cached = VideoTranscriptionCache.load(cache_file)
                if cached and cached.segments:
                    segments = cached.segments
                    self.progress_update.emit(self.video_path, "Trascrizione trovata in cache", 40)

            if not segments:
                self.progress_update.emit(self.video_path, "Ascolto radio istruttore (Whisper)...", 30)
                detector = PilotDetector(pilots_list=self.pilot_names, transcriber=self.transcriber)
                # Rimuovi file cache vecchio per rigenerarlo pulito col nuovo modello
                if os.path.exists(cache_file):
                    try:
                        os.remove(cache_file)
                    except Exception:
                        pass
                m = detector.identify_pilot_from_audio(self.video_path)
                segments = getattr(m, "segments", [])

            print(f"\n[Whisper Log] --- Trascrizione audio per {base_name} ({len(segments)} segmenti trovati) ---")
            for seg in segments:
                print(f"  [{seg.start:6.2f}s - {seg.end:6.2f}s] \"{seg.text}\"")

            self.progress_update.emit(self.video_path, f"Analisi manovre su {len(segments)} frasi...", 70)
            if segments:
                detected_chaps = self.maneuver_detector.detect_chapters(segments)
                print(f"[Whisper Log] Manovre rilevate: {len(detected_chaps)}")
                ch_dicts = []
                for ch in detected_chaps:
                    print(f"  -> [{ch.start_time:.1f}s] {ch.maneuver_name} (Comando: \"{ch.transcription_text}\")")
                    ch_dicts.append({
                        "title": ch.maneuver_name,
                        "start": round(ch.start_time, 2),
                        "end": round(ch.end_time, 2),
                        "instructor_command": ch.transcription_text,
                        "notes": ch.category
                    })
                sc.chapters = ch_dicts
                sc.save()
                self.progress_update.emit(self.video_path, f"{len(ch_dicts)} manovre rilevate", 100)
                self.maneuvers_ready.emit(self.video_path, ch_dicts)
            else:
                self.progress_update.emit(self.video_path, "Nessun comando radio rilevato", 100)
                self.maneuvers_ready.emit(self.video_path, [])
        except Exception as e:
            print(f"[ManeuverWorker] Errore su {self.video_path}: {e}")
            self.progress_update.emit(self.video_path, "Errore analisi manovre", 100)
