import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from thefuzz import fuzz
from core.transcriber import TranscriptionSegment

@dataclass
class SIVChapter:
    start_time: float      # in secondi
    end_time: float        # in secondi
    maneuver_id: str
    maneuver_name: str
    category: str
    transcription_text: str
    confidence: float

    @property
    def formatted_start(self) -> str:
        """Restituisce il tempo nel formato MM:SS o HH:MM:SS per YouTube / capitoli."""
        total_seconds = int(self.start_time)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

class ManeuverDetector:
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = str(Path(__file__).parent.parent / "config" / "siv_maneuvers.json")
        self.config_path = config_path
        self.maneuvers = self._load_maneuvers()

    def _load_maneuvers(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("maneuvers", [])

    def detect_chapters(self, segments: List[TranscriptionSegment], min_score: int = 70, min_gap_seconds: float = 12.0) -> List[SIVChapter]:
        """
        Analizza i segmenti trascritti e individua i comandi delle manovre.
        min_score: punteggio minimo di fuzzy matching (0-100).
        min_gap_seconds: intervallo minimo tra due capitoli della stessa manovra per evitare duplicati.
        """
        detected_chapters: List[SIVChapter] = []

        for seg in segments:
            text_lower = seg.text.lower()
            best_match = None
            best_score = 0

            for m in self.maneuvers:
                m_name = m["name"]
                m_id = m["id"]
                category = m["category"]
                
                for kw in m["keywords"]:
                    kw_lower = kw.lower()
                    # Controllo sottostringa esatta (alta priorità)
                    if kw_lower in text_lower:
                        score = 95
                    else:
                        # Fuzzy partial ratio
                        score = fuzz.partial_ratio(kw_lower, text_lower)
                    
                    if score > best_score and score >= min_score:
                        best_score = score
                        best_match = (m_id, m_name, category)

            if best_match:
                m_id, m_name, category = best_match
                
                # Evita duplicazioni ravvicinate
                is_duplicate = False
                for prev in reversed(detected_chapters):
                    if (seg.start - prev.start_time) < min_gap_seconds:
                        if prev.maneuver_id == m_id:
                            is_duplicate = True
                            break
                    else:
                        break

                if not is_duplicate:
                    chapter = SIVChapter(
                        start_time=seg.start,
                        end_time=seg.end,
                        maneuver_id=m_id,
                        maneuver_name=m_name,
                        category=category,
                        transcription_text=seg.text,
                        confidence=best_score / 100.0
                    )
                    detected_chapters.append(chapter)

        return detected_chapters

    def export_youtube_format(self, chapters: List[SIVChapter]) -> str:
        """Formatta i capitoli per la descrizione di YouTube."""
        lines = []
        # Se il primo capitolo non parte da 00:00, aggiungi Intro/Decollo
        if not chapters or chapters[0].start_time > 5.0:
            lines.append("00:00 Decollo / Preparazione")
        for ch in chapters:
            lines.append(f"{ch.formatted_start} {ch.maneuver_name}")
        return "\n".join(lines)
