import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set
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

DEFAULT_REPEAT_PHRASES = [
    "fanne un'altra", "facciamone un'altra", "fanne un altra", "facciamone un altra",
    "riproviamo", "riprova", "ancora una", "falla ancora", "rifalla",
    "un'altra uguale", "un altra uguale", "stessa cosa", "ripeti", "altra volta",
    "falla di nuovo", "facciamo la stessa", "ancora una volta"
]

class ManeuverDetector:
    def __init__(self, config_path: Optional[str] = None, custom_config_path: Optional[str] = None):
        base_dir = Path(__file__).parent.parent / "config"
        if config_path is None:
            config_path = str(base_dir / "siv_maneuvers.json")
        if custom_config_path is None:
            custom_config_path = str(base_dir / "siv_maneuvers_custom.json")

        self.config_path = config_path
        self.custom_config_path = custom_config_path

        self.all_maneuvers = []
        self.repeat_phrases: List[str] = list(DEFAULT_REPEAT_PHRASES)
        self.enabled_maneuver_ids: Optional[set] = None

        self._load_configuration()

    def _load_configuration(self):
        # 1. Carica default
        default_data = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    default_data = json.load(f)
            except Exception as e:
                print(f"[ManeuverDetector] Errore caricamento default: {e}")

        # 2. Carica custom se presente, altrimenti usa default
        data_to_use = default_data
        if os.path.exists(self.custom_config_path):
            try:
                with open(self.custom_config_path, "r", encoding="utf-8") as f:
                    custom_data = json.load(f)
                    if custom_data.get("maneuvers"):
                        data_to_use = custom_data
            except Exception as e:
                print(f"[ManeuverDetector] Errore caricamento custom: {e}")

        self.all_maneuvers = data_to_use.get("maneuvers", [])
        
        # Carica frasi di retry personalizzate se presenti
        if "repeat_phrases" in data_to_use and isinstance(data_to_use["repeat_phrases"], list):
            self.repeat_phrases = [str(rp).strip().lower() for rp in data_to_use["repeat_phrases"] if str(rp).strip()]
        else:
            self.repeat_phrases = list(DEFAULT_REPEAT_PHRASES)

        # Carica set di manovre abilitate
        if "enabled_ids" in data_to_use and isinstance(data_to_use["enabled_ids"], list):
            self.enabled_maneuver_ids = set(data_to_use["enabled_ids"])
        else:
            self.enabled_maneuver_ids = {m["id"] for m in self.all_maneuvers}

    def save_configuration(self, maneuvers: Optional[List[dict]] = None, enabled_ids: Optional[List[str]] = None, repeat_phrases: Optional[List[str]] = None):
        if maneuvers is not None:
            self.all_maneuvers = maneuvers
        if enabled_ids is not None:
            self.enabled_maneuver_ids = set(enabled_ids)
        if repeat_phrases is not None:
            self.repeat_phrases = [str(rp).strip().lower() for rp in repeat_phrases if str(rp).strip()]

        out_data = {
            "maneuvers": self.all_maneuvers,
            "enabled_ids": list(self.enabled_maneuver_ids) if self.enabled_maneuver_ids is not None else [m["id"] for m in self.all_maneuvers],
            "repeat_phrases": self.repeat_phrases
        }

        os.makedirs(os.path.dirname(self.custom_config_path), exist_ok=True)
        with open(self.custom_config_path, "w", encoding="utf-8") as f:
            json.dump(out_data, f, ensure_ascii=False, indent=2)

    def reset_to_defaults(self):
        if os.path.exists(self.custom_config_path):
            try:
                os.remove(self.custom_config_path)
            except Exception:
                pass
        self._load_configuration()

    @property
    def active_maneuvers(self) -> List[dict]:
        if self.enabled_maneuver_ids is None:
            return self.all_maneuvers
        return [m for m in self.all_maneuvers if m.get("id") in self.enabled_maneuver_ids]

    def _is_repeat_trigger(self, text: str) -> bool:
        text_l = text.lower()
        for rp in self.repeat_phrases:
            if rp in text_l:
                return True
            if len(rp) >= 7 and fuzz.partial_ratio(rp, text_l) >= 88:
                return True
        return False

    def detect_chapters(self, segments: List[TranscriptionSegment], min_score: int = 70, min_gap_seconds: float = 12.0) -> List[SIVChapter]:
        """
        Analizza i segmenti trascritti e individua i comandi delle manovre.
        Supporta:
        1. Riconoscimento mirato tramite le sole manovre attive configurate.
        2. Sliding Context Window per agganciare il comando esecutivo ('vai', 'tira', '3 2 1').
        3. Riconoscimento delle frasi di retry ('fanne un'altra', 'riproviamo') con
           ereditarietà della manovra precedente nello stesso volo.
        """
        detected_chapters: List[SIVChapter] = []
        action_triggers = ["vai", "tira", "chiudi", "adesso", "ora", "3, 2, 1", "3 2 1", "giù", "sfonda", "via"]
        last_identified_maneuver = None  # (m_id, m_name, category)

        maneuvers_pool = self.active_maneuvers

        for i, seg in enumerate(segments):
            text_lower = seg.text.lower()
            
            # Contesto allargato: segmento corrente + segmento successivo se entro 7 secondi
            combined_text = text_lower
            target_start = seg.start
            target_end = seg.end
            
            if i + 1 < len(segments):
                next_seg = segments[i + 1]
                if (next_seg.start - seg.end) <= 7.0:
                    combined_text = f"{text_lower} {next_seg.text.lower()}"
                    for act in action_triggers:
                        if act in next_seg.text.lower():
                            target_start = next_seg.start
                            target_end = next_seg.end
                            break

            best_match = None
            best_score = 0

            # 1. Cerca match tra le manovre attive
            for m in maneuvers_pool:
                m_name = m["name"]
                m_id = m["id"]
                category = m.get("category", "SIV")
                
                for kw in m.get("keywords", []):
                    kw_lower = kw.lower()
                    if kw_lower in text_lower or kw_lower in combined_text:
                        score = 95
                    elif len(kw_lower) >= 6:
                        score = max(
                            fuzz.partial_ratio(kw_lower, text_lower),
                            fuzz.partial_ratio(kw_lower, combined_text)
                        )
                        if score < 82:
                            score = 0
                    else:
                        score = 0
                    
                    if score > best_score and score >= min_score:
                        best_score = score
                        best_match = (m_id, m_name, category)

            # 2. Se non c'è match diretto, verifica se è un comando di ripetizione/retry della manovra precedente
            is_repeat = False
            if best_match is None and last_identified_maneuver is not None:
                if self._is_repeat_trigger(text_lower) or self._is_repeat_trigger(combined_text):
                    # Assegna la manovra precedente
                    m_id, m_name, category = last_identified_maneuver
                    best_match = (m_id, m_name, category)
                    best_score = 90
                    is_repeat = True

            if best_match:
                m_id, m_name, category = best_match
                
                # Evita duplicazioni troppo ravvicinate
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
                        start_time=target_start,
                        end_time=target_end,
                        maneuver_id=m_id,
                        maneuver_name=m_name,
                        category=category,
                        transcription_text=seg.text,
                        confidence=best_score / 100.0
                    )
                    detected_chapters.append(chapter)
                    # Aggiorna l'ultima manovra valida eseguita
                    last_identified_maneuver = (m_id, m_name, category)

        return detected_chapters

    def export_youtube_format(self, chapters: List[SIVChapter]) -> str:
        """Formatta i capitoli per la descrizione di YouTube."""
        lines = []
        if not chapters or chapters[0].start_time > 5.0:
            lines.append("00:00 Decollo / Preparazione")
        for ch in chapters:
            lines.append(f"{ch.formatted_start} {ch.maneuver_name}")
        return "\n".join(lines)

