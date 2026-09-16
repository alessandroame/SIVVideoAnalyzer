import os
import time
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtCore import QThread, pyqtSignal

from core.sidecar_manager import SidecarData
from core.pilot_detector import PilotDetector, VideoPilotMatch, VideoTranscriptionCache
from core.maneuver_detector import ManeuverDetector
from core.wing_color_detector import detect_wing_colors_from_video, match_detected_colors_to_pilots

class AnalysisWorker(QThread):
    clip_analyzed = pyqtSignal(object)              # emette VideoPilotMatch combinato
    clip_progress = pyqtSignal(str, float, float)   # video_path, sec_fatti, sec_totali (audio)
    audio_analyzed = pyqtSignal(str, float, str, str) # video_path, confidenza, frase, pilota_audio
    wing_analyzed = pyqtSignal(str, list, float, str)  # video_path, colori, confidenza, pilota_visivo
    overall_progress = pyqtSignal(str, int)         # eta_text, percent_globale
    phases_status = pyqtSignal(int, int, int, int, int)  # audio_done, wing_done, man_done, track_done, total_clips
    status_update = pyqtSignal(str)
    maneuvers_ready = pyqtSignal(str, list)         # video_path, list of chapters
    maneuver_progress = pyqtSignal(str, str, int)   # video_path, status_text, percent
    tracking_ready = pyqtSignal(str, dict)          # video_path, tracking_dict
    tracking_progress = pyqtSignal(str, str, int)   # video_path, status_text, percent


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
                self.maneuver_progress.emit(video_path, "Ascolto comandi radio (Whisper)...", 25)

                def on_man_prog(curr_s, total_s):
                    if not self._is_cancelled:
                        dur = max(0.1, total_s)
                        whisper_pct = int(min(1.0, curr_s / dur) * 45.0)
                        self.maneuver_progress.emit(video_path, f"Trascrizione radio: {int(curr_s)}s/{int(total_s)}s", 25 + whisper_pct)

                m = detector.identify_pilot_from_audio(
                    video_path,
                    progress_callback=on_man_prog,
                    is_cancelled_callback=lambda: self._is_cancelled,
                    quick_probe=False
                )
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

    def _process_tracking_for_video(self, video_path: str):
        """Estrae e calcola in background il tracciamento di Pilota e Vela per il video indicato."""
        try:
            sc = SidecarData(video_path)
            if sc.has_tracking():
                self.tracking_progress.emit(video_path, "Tracciamento già presente", 100)
                self.tracking_ready.emit(video_path, sc.tracking)
                return

            self.tracking_progress.emit(video_path, "Avvio tracciamento Pilota & Vela...", 10)
            from core.tracking.pipeline import VideoTrackingPipeline
            pipeline = VideoTrackingPipeline(sample_interval=0.04)

            def on_track_prog(pct: int, msg: str):
                if not self._is_cancelled:
                    self.tracking_progress.emit(video_path, msg, pct)

            def is_canc() -> bool:
                return self._is_cancelled

            tracking_result = pipeline.process_video(
                video_path=video_path,
                progress_callback=on_track_prog,
                is_cancelled=is_canc
            )

            if self._is_cancelled:
                return

            if tracking_result:
                sc.tracking = tracking_result
                sc.save()
                self.tracking_progress.emit(video_path, "Tracciamento completato", 100)
                self.tracking_ready.emit(video_path, tracking_result)
            else:
                self.tracking_progress.emit(video_path, "Nessun dato di tracciamento", 100)
        except Exception as e:
            print(f"[AnalysisWorker] Errore tracking su {video_path}: {e}")
            self.tracking_progress.emit(video_path, f"Errore tracking: {e}", 100)

    def run(self):
        detector = PilotDetector(pilots_list=self.pilot_names, transcriber=self.transcriber)
        man_detector = self.maneuver_detector

        # =====================================================================
        # PREEMPTION P1: Se c'è un video prioritario aperto, calcola subito manovre & tracking
        # =====================================================================
        if self.priority_video:
            self.status_update.emit(f"⚡ Rilevamento immediato manovre e tracking: {os.path.basename(self.priority_video)}...")
            self._process_maneuvers_for_video(self.priority_video, detector, man_detector)
            self._process_tracking_for_video(self.priority_video)

        total_clips = len(self.video_files)

        # =====================================================================
        # FASE 1: IDENTIFICAZIONE RAPIDA PILOTI (Radio Check 90s + Colori Vela)
        # =====================================================================
        self.status_update.emit("🔍 Avvio Fase 1: Identificazione rapida piloti...")
        fase1_start_time = time.time()
        fase1_done = 0

        for i, vf in enumerate(self.video_files):
            if self._is_cancelled:
                return

            if self._requested_priority:
                p_vid = self._requested_priority
                self._requested_priority = None
                self._process_maneuvers_for_video(p_vid, detector, man_detector)
                self._process_tracking_for_video(p_vid)

            fname = os.path.basename(vf)
            sc = SidecarData(vf)

            # Se il pilota è già stato identificato in precedenza, emettilo subito
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
                    wing_colors=sc.wing_colors,
                    audio_confidence=sc.audio_confidence or calc_conf,
                    wing_confidence=sc.wing_confidence or (0.75 if sc.wing_colors else 0.0)
                )
                self.audio_analyzed.emit(vf, m.audio_confidence, sc.radio_phrase, sc.pilot_name)
                self.wing_analyzed.emit(vf, sc.wing_colors, m.wing_confidence, sc.pilot_name)
                self.clip_analyzed.emit(m)
                self.clip_progress.emit(vf, 100.0, 100.0)
                fase1_done += 1
                self.phases_status.emit(fase1_done, fase1_done, 0, 0, total_clips)
                continue

            self.status_update.emit(f"[Fase 1/3] Identificazione rapida (Radio 30s + Vela): {fname} ({i+1}/{total_clips})...")

            def on_file_prog(curr_s, dur_s):
                if not self._is_cancelled:
                    self.clip_progress.emit(vf, curr_s, dur_s)

            # Feedback immediato sulla riga della tabella
            self.clip_progress.emit(vf, 1.0, 30.0)

            try:
                # Esecuzione parallela: ThreadPoolExecutor esegue contemporaneamente:
                # 1. Analisi Colore Vela dai frame video
                # 2. Probe Audio max 30s con Whisper (con EARLY EXIT immediato se il nome è riconosciuto nei primi secondi)
                with ThreadPoolExecutor(max_workers=2) as executor:
                    wing_future = executor.submit(detect_wing_colors_from_video, vf, 0.0)
                    audio_future = executor.submit(
                        detector.identify_pilot_from_audio,
                        vf,
                        progress_callback=on_file_prog,
                        is_cancelled_callback=lambda: self._is_cancelled,
                        quick_probe=True,
                        max_probe_seconds=30.0
                    )
                    
                    # Ritiro risultati
                    detected_cols = wing_future.result()
                    m = audio_future.result()

                if self._is_cancelled:
                    return

                # Elabora esito audio
                audio_detected_pilot = m.detected_pilot
                audio_conf = m.confidence
                radio_phrase = " | ".join(m.matched_phrases) if m.matched_phrases else ""
                m.audio_confidence = audio_conf
                self.audio_analyzed.emit(vf, audio_conf, radio_phrase, audio_detected_pilot)

                # Elabora esito vela
                wing_detected_pilot = ""
                wing_conf = 0.0
                if detected_cols:
                    sc.wing_colors = [{"name": c[0], "hex": c[1]} for c in detected_cols]
                    m.wing_colors = sc.wing_colors
                    if self.pilot_gliders:
                        color_match = match_detected_colors_to_pilots(detected_cols, self.pilot_gliders)
                        if color_match:
                            matched_pilot_key, col_conf = color_match
                            wing_conf = col_conf
                            for orig_p in self.pilot_names:
                                if orig_p.lower() == matched_pilot_key.lower():
                                    wing_detected_pilot = orig_p
                                    break

                m.wing_confidence = wing_conf
                self.wing_analyzed.emit(vf, m.wing_colors, wing_conf, wing_detected_pilot)

                # Fusione/Decisione pilota:
                # Se l'audio non ha trovato il pilota o è incerto ma la vela corrisponde:
                if (not m.detected_pilot or m.detected_pilot in ["In attesa...", "Da Assegnare"]) and wing_detected_pilot:
                    m.detected_pilot = wing_detected_pilot
                    m.confidence = wing_conf
                    m.matched_phrases.append(f"Matching Visivo Colore Vela: {', '.join([c[0] for c in detected_cols])}")

                sc.pilot_name = m.detected_pilot
                sc.flight_number = m.flight_number or 1
                sc.confidence = m.confidence
                sc.audio_confidence = audio_conf
                sc.wing_confidence = wing_conf
                if m.matched_phrases:
                    sc.radio_phrase = " | ".join(m.matched_phrases)
                sc.save()

                self.clip_analyzed.emit(m)
                self.clip_progress.emit(vf, 100.0, 100.0)

            except Exception as e:
                print(f"[Worker] Errore Fase 1 su {fname}: {e}")

            fase1_done += 1
            f1_pct = int((fase1_done / total_clips) * 100)
            self.phases_status.emit(fase1_done, fase1_done, 0, 0, total_clips)
            self.overall_progress.emit(f"🚀 Fase 1/3: Piloti identificati ({fase1_done}/{total_clips} clip)", f1_pct)

        # =====================================================================
        # FASE 2: RILEVAMENTO APPROFONDITO MANOVRE & CAPITOLI SIV
        # =====================================================================
        self.status_update.emit("🎯 Avvio Fase 2: Rilevamento completo manovre & capitoli...")
        fase2_start_time = time.time()
        fase2_done = 0

        for i, vf in enumerate(self.video_files):
            if self._is_cancelled:
                return

            # Controlla priorità interattiva (se l'utente apre un video nel player)
            if self._requested_priority:
                p_vid = self._requested_priority
                self._requested_priority = None
                self._process_maneuvers_for_video(p_vid, detector, man_detector)
                self._process_tracking_for_video(p_vid)

            fname = os.path.basename(vf)
            sc = SidecarData(vf)

            if sc.chapters:
                fase2_done += 1
                self.maneuver_progress.emit(vf, f"{len(sc.chapters)} manovre caricate", 100)
                self.maneuvers_ready.emit(vf, sc.chapters)
                self.phases_status.emit(total_clips, total_clips, fase2_done, 0, total_clips)
                continue

            self.status_update.emit(f"[Fase 2/3] Analisi manovre: {fname} ({i+1}/{total_clips})...")
            self._process_maneuvers_for_video(vf, detector, man_detector)

            fase2_done += 1
            f2_pct = int((fase2_done / total_clips) * 100)
            elapsed_f2 = time.time() - fase2_start_time
            avg_f2 = elapsed_f2 / max(1, fase2_done)
            rem_f2 = total_clips - fase2_done
            est_rem_sec = int(avg_f2 * rem_f2)
            m_rem = est_rem_sec // 60
            s_rem = est_rem_sec % 60

            self.phases_status.emit(total_clips, total_clips, fase2_done, 0, total_clips)
            if rem_f2 > 0:
                eta_str = f"⏱ Fase 2/3: Rilevamento manovre ({fase2_done}/{total_clips}) - ~{m_rem:02d}m {s_rem:02d}s rimanenti"
            else:
                eta_str = f"✅ Manovre completate ({total_clips} clip)"

            self.overall_progress.emit(eta_str, f2_pct)

        # =====================================================================
        # FASE 3: CALCOLO TRACCIAMENTO PILOTA & VELA (Accodato in background)
        # =====================================================================
        self.status_update.emit("📍 Avvio Fase 3: Calcolo tracciamento Pilota & Vela in background...")
        fase3_start_time = time.time()
        fase3_done = 0

        for i, vf in enumerate(self.video_files):
            if self._is_cancelled:
                return

            if self._requested_priority:
                p_vid = self._requested_priority
                self._requested_priority = None
                self._process_maneuvers_for_video(p_vid, detector, man_detector)
                self._process_tracking_for_video(p_vid)

            fname = os.path.basename(vf)
            sc = SidecarData(vf)

            if sc.has_tracking():
                fase3_done += 1
                self.tracking_progress.emit(vf, "Tracciamento già presente", 100)
                self.tracking_ready.emit(vf, sc.tracking)
                self.phases_status.emit(total_clips, total_clips, total_clips, fase3_done, total_clips)
                continue

            self.status_update.emit(f"[Fase 3/3] Tracciamento: {fname} ({i+1}/{total_clips})...")
            self._process_tracking_for_video(vf)

            fase3_done += 1
            f3_pct = int((fase3_done / total_clips) * 100)
            self.phases_status.emit(total_clips, total_clips, total_clips, fase3_done, total_clips)
            elapsed_f3 = time.time() - fase3_start_time
            avg_f3 = elapsed_f3 / max(1, fase3_done)
            rem_f3 = total_clips - fase3_done
            est_rem_sec = int(avg_f3 * rem_f3)
            m_rem = est_rem_sec // 60
            s_rem = est_rem_sec % 60

            if rem_f3 > 0:
                eta_str = f"⏱ Fase 3/3: Tracciamento ({fase3_done}/{total_clips}) - ~{m_rem:02d}m {s_rem:02d}s rimanenti"
            else:
                eta_str = f"✅ Analisi completa, manovre e tracciamento terminati ({total_clips} clip)"

            self.overall_progress.emit(eta_str, f3_pct)

        self.status_update.emit("Analisi, manovre e tracciamento completati con successo.")
