import os
import re
from dataclasses import dataclass
from typing import List, Optional, Dict
from thefuzz import fuzz
from core.audio_extractor import extract_audio
from core.transcriber import SIVTranscriber, TranscriptionSegment

@dataclass
class VideoPilotMatch:
    video_path: str
    filename: str
    detected_pilot: str
    confidence: float
    matched_phrases: List[str]

class PilotDetector:
    def __init__(self, pilots_list: Optional[List[str]] = None, transcriber: Optional[SIVTranscriber] = None):
        """
        pilots_list: elenco dei nomi o nomi e cognomi dei piloti attesi.
        """
        self.pilots_list = [p.strip() for p in pilots_list] if pilots_list else []
        self.transcriber = transcriber or SIVTranscriber(model_size="base")

    def set_pilots_list(self, pilots: List[str]):
        self.pilots_list = [p.strip() for p in pilots if p.strip()]

    def identify_pilot_from_audio(self, video_path: str, temp_dir: str = "temp") -> VideoPilotMatch:
        """
        Estrae i primi minuti dell'audio del video, trascrive e cerca riferimenti ai piloti.
        """
        os.makedirs(temp_dir, exist_ok=True)
        fname = os.path.basename(video_path)
        base_name = os.path.splitext(fname)[0]
        wav_path = os.path.join(temp_dir, f"{base_name}_pilot_check.wav")
        
        # Estrai audio
        extract_audio(video_path, wav_path)
        
        # Trascrivi con Whisper
        segments = self.transcriber.transcribe(wav_path, language="it")
        
        # Pulisci file audio temporaneo
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

        return self.match_pilot_from_segments(video_path, segments)

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
            matched_phrases=best_phrases[:3]
        )
