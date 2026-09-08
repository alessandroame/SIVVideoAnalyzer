import os
import re
from dataclasses import dataclass
from typing import List, Optional, Dict
from thefuzz import fuzz
from core.audio_extractor import extract_audio, get_video_duration
from core.transcriber import SIVTranscriber, TranscriptionSegment
from core.timeline_merger import VideoTranscriptionCache

@dataclass
class VideoPilotMatch:
    video_path: str
    filename: str
    detected_pilot: str
    confidence: float
    matched_phrases: List[str]
    duration: float = 0.0
    flight_number: Optional[int] = None
    segments: List[TranscriptionSegment] = None

    def __post_init__(self):
        if self.segments is None:
            self.segments = []

class PilotDetector:
    def __init__(self, pilots_list: Optional[List[str]] = None, transcriber: Optional[SIVTranscriber] = None):
        """
        pilots_list: elenco dei nomi o nomi e cognomi dei piloti attesi.
        """
        self.pilots_list = [p.strip() for p in pilots_list] if pilots_list else []
        self.transcriber = transcriber or SIVTranscriber(model_size="small")

    def set_pilots_list(self, pilots: List[str]):
        self.pilots_list = [p.strip() for p in pilots if p.strip()]

    def identify_pilot_from_audio(self, video_path: str, temp_dir: str = "temp", progress_callback=None, is_cancelled_callback=None) -> VideoPilotMatch:
        """
        Estrae l'audio, calcola la durata, trascrive una sola volta (salvando in cache) e identifica il pilota.
        """
        os.makedirs(temp_dir, exist_ok=True)
        fname = os.path.basename(video_path)
        base_name = os.path.splitext(fname)[0]
        cache_file = os.path.join(temp_dir, f"{base_name}_cache.json")
        
        # 1. Controlla se la trascrizione è già in cache su disco
        cached = VideoTranscriptionCache.load(cache_file)
        if cached:
            duration = cached.duration
            segments = cached.segments
            if progress_callback:
                progress_callback(duration, duration)
        else:
            duration = get_video_duration(video_path)
            wav_path = os.path.join(temp_dir, f"{base_name}_audio.wav")
            extract_audio(video_path, wav_path)
            
            def on_segment(seg):
                if progress_callback and duration > 0:
                    progress_callback(seg.end, duration)

            segments = self.transcriber.transcribe(
                wav_path, 
                language="it", 
                progress_callback=on_segment,
                is_cancelled_callback=is_cancelled_callback
            )
            
            # Salva in cache solo se non è stato interrotto
            if not (is_cancelled_callback and is_cancelled_callback()):
                new_cache = VideoTranscriptionCache(
                    video_path=video_path,
                    filename=fname,
                    duration=duration,
                    segments=segments
                )
                new_cache.save(cache_file)
            
            # Pulisci file audio temporaneo
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

        match = self.match_pilot_from_segments(video_path, segments)
        match.duration = duration
        match.segments = segments
        return match

    def match_pilot_from_segments(self, video_path: str, segments: List[TranscriptionSegment]) -> VideoPilotMatch:
        fname = os.path.basename(video_path)
        
        # 1. Se nel nome del file c'è già il nome di un pilota noto
        for p in self.pilots_list:
            if p.lower() in fname.lower():
                return VideoPilotMatch(
                    video_path=video_path,
                    filename=fname,
                    detected_pilot=p,
                    confidence=1.0,
                    matched_phrases=[f"Nome trovato nel file: {fname}"]
                )

        # 2. Riconoscimento dalle frasi radio
        # L'istruttore chiama di solito con: "Nome, mi ricevi?", "Ok Nome vai", "Nome pronto?"
        call_patterns = [
            r"\b(?:ciao|ok|vai|pronto|ricevi|chiudi|ascolta|bravo)\s+([A-Za-zÀ-ÿ]+)\b",
            r"\b([A-Za-zÀ-ÿ]+)\s+(?:mi ricevi|ci sei|sei pronto|in box|pronto per|vai)\b"
        ]

        candidate_scores: Dict[str, float] = {p: 0.0 for p in self.pilots_list}
        matched_phrases: Dict[str, List[str]] = {p: [] for p in self.pilots_list}

        for seg in segments:
            text = seg.text
            text_lower = text.lower()

            for pilot in self.pilots_list:
                p_lower = pilot.lower()
                # Split per nome e cognome
                tokens = p_lower.split()
                
                # Match esatto parola intera
                for token in tokens:
                    if len(token) > 2 and re.search(rf"\b{re.escape(token)}\b", text_lower):
                        candidate_scores[pilot] += 1.5
                        matched_phrases[pilot].append(f"[{seg.start:.1f}s] \"{seg.text}\"")

                # Match fuzzy su frase
                score = fuzz.partial_ratio(p_lower, text_lower)
                if score >= 85:
                    candidate_scores[pilot] += 1.0
                    matched_phrases[pilot].append(f"[{seg.start:.1f}s] \"{seg.text}\"")

        # 3. Riconoscimento vocale radio del NUMERO DI VOLO
        # Cerca pattern tipo: "primo volo", "volo uno", "secondo volo", "volo 2", "terzo volo", ecc.
        detected_flight_num = None
        flight_patterns = [
            (r"\b(?:primo|1°|uno)\s+volo\b|\bvolo\s+(?:uno|1|1°)\b", 1),
            (r"\b(?:secondo|2°|due)\s+volo\b|\bvolo\s+(?:due|2|2°)\b", 2),
            (r"\b(?:terzo|3°|tre)\s+volo\b|\bvolo\s+(?:tre|3|3°)\b", 3),
            (r"\b(?:quarto|4°|quattro)\s+volo\b|\bvolo\s+(?:quattro|4|4°)\b", 4),
            (r"\b(?:quinto|5°|cinque)\s+volo\b|\bvolo\s+(?:cinque|5|5°)\b", 5),
            (r"\b(?:sesto|6°|sei)\s+volo\b|\bvolo\s+(?:sei|6|6°)\b", 6),
            (r"\b(?:settimo|7°|sette)\s+volo\b|\bvolo\s+(?:sette|7|7°)\b", 7),
            (r"\b(?:ottavo|8°|otto)\s+volo\b|\bvolo\s+(?:otto|8|8°)\b", 8),
        ]

        for seg in segments:
            txt_low = seg.text.lower()
            for pattern, f_num in flight_patterns:
                if re.search(pattern, txt_low):
                    detected_flight_num = f_num
                    break
            if detected_flight_num:
                break

        # Trova il pilota con il punteggio più alto
        best_pilot = "Da Assegnare"
        highest_score = 0.0
        best_phrases = []

        for pilot, score in candidate_scores.items():
            if score > highest_score and score >= 1.5:
                highest_score = score
                best_pilot = pilot
                best_phrases = matched_phrases[pilot]

        confidence = min(1.0, highest_score / 4.0) if highest_score > 0 else 0.0

        return VideoPilotMatch(
            video_path=video_path,
            filename=fname,
            detected_pilot=best_pilot,
            confidence=confidence,
            matched_phrases=best_phrases[:3],
            flight_number=detected_flight_num
        )
