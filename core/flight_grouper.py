import os
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from core.transcriber import TranscriptionSegment
from core.maneuver_detector import SIVChapter

@dataclass
class FlightClipInfo:
    filename: str
    video_path: str
    duration: float = 0.0
    start_timestamp: float = 0.0  # Unix timestamp di inizio registrazione
    offset_in_flight: float = 0.0 # Offset temporale cumulativo all'interno del volo

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'FlightClipInfo':
        return cls(**data)

@dataclass
class SIVFlight:
    flight_number: int            # es. 1, 2, 3
    flight_id: str                # es. "Volo_01"
    pilot_name: str
    clips: List[FlightClipInfo] = field(default_factory=list)
    segments: List[TranscriptionSegment] = field(default_factory=list)
    chapters: List[SIVChapter] = field(default_factory=list)
    notes: str = ""

    @property
    def total_duration(self) -> float:
        return sum(c.duration for c in self.clips)

    def calculate_offsets(self):
        """Calcola l'offset temporale cumulativo per ciascuna clip del volo."""
        offset = 0.0
        for clip in self.clips:
            clip.offset_in_flight = offset
            offset += clip.duration

    def get_clip_and_local_time(self, global_flight_time: float):
        """Dato un minutaggio all'interno del volo unificato, trova la clip esatta e il minutaggio locale."""
        for clip in self.clips:
            if clip.offset_in_flight <= global_flight_time < (clip.offset_in_flight + clip.duration):
                return clip, (global_flight_time - clip.offset_in_flight)
        if self.clips:
            last_clip = self.clips[-1]
            return last_clip, max(0.0, global_flight_time - last_clip.offset_in_flight)
        return None, 0.0

    def to_dict(self) -> dict:
        return {
            'flight_number': self.flight_number,
            'flight_id': self.flight_id,
            'pilot_name': self.pilot_name,
            'total_duration': self.total_duration,
            'notes': self.notes,
            'clips': [c.to_dict() for c in self.clips],
            'segments': [asdict(s) for s in self.segments],
            'chapters': [
                {
                    'start_time': ch.start_time,
                    'end_time': ch.end_time,
                    'formatted_start': ch.formatted_start,
                    'maneuver_id': ch.maneuver_id,
                    'maneuver_name': ch.maneuver_name,
                    'category': ch.category,
                    'transcription_text': ch.transcription_text,
                    'confidence': ch.confidence
                } for ch in self.chapters
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SIVFlight':
        clips = [FlightClipInfo.from_dict(c) for c in data.get('clips', [])]
        segments = [TranscriptionSegment(**s) for s in data.get('segments', [])]
        chapters = []
        for ch in data.get('chapters', []):
            chapters.append(SIVChapter(
                start_time=ch['start_time'],
                end_time=ch['end_time'],
                maneuver_id=ch.get('maneuver_id', ''),
                maneuver_name=ch.get('maneuver_name', ''),
                category=ch.get('category', ''),
                transcription_text=ch.get('transcription_text', ''),
                confidence=ch.get('confidence', 1.0)
            ))
        flight = cls(
            flight_number=data.get('flight_number', 1),
            flight_id=data.get('flight_id', f"Volo_{data.get('flight_number', 1):02d}"),
            pilot_name=data.get('pilot_name', ''),
            clips=clips,
            segments=segments,
            chapters=chapters,
            notes=data.get('notes', '')
        )
        flight.calculate_offsets()
        return flight

    def save_to_folder(self, flight_folder: str):
        """Salva i metadati completi del volo nella cartella del volo."""
        os.makedirs(flight_folder, exist_ok=True)
        meta_file = os.path.join(flight_folder, "volo_info.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        # Salva anche i capitoli in formato testuale esportabile
        from core.maneuver_detector import ManeuverDetector
        yt_text = ManeuverDetector().export_youtube_format(self.chapters)
        with open(os.path.join(flight_folder, "capitoli_youtube.txt"), "w", encoding="utf-8") as f:
            f.write(yt_text)

    @classmethod
    def load_from_folder(cls, flight_folder: str) -> Optional['SIVFlight']:
        meta_file = os.path.join(flight_folder, "volo_info.json")
        if not os.path.exists(meta_file):
            return None
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception:
            return None


class FlightGrouper:
    def __init__(self, time_gap_threshold_seconds: float = 1200.0):
        """
        time_gap_threshold_seconds: soglia di stacco tra clip (default 20 minuti = 1200s).
        Clip registrate entro questa soglia appartengono allo stesso volo.
        """
        self.time_gap_threshold_seconds = time_gap_threshold_seconds

    def group_pilot_matches_into_flights(self, pilot_name: str, matches: list) -> List[SIVFlight]:
        """
        Data una lista di VideoPilotMatch per un pilota, li ordina cronologicamente
        e li raggruppa in uno o più SIVFlight (multi-clip compatibile).
        """
        if not matches:
            return []

        # Ordina cronologicamente in base al timestamp di modifica del file
        def get_file_time(m):
            try:
                return os.path.getmtime(m.video_path)
            except Exception:
                return 0.0

        sorted_matches = sorted(matches, key=get_file_time)

        flight_groups = []
        current_group = [sorted_matches[0]]

        for i in range(1, len(sorted_matches)):
            prev_m = sorted_matches[i - 1]
            curr_m = sorted_matches[i]
            
            t_prev = get_file_time(prev_m) + prev_m.duration
            t_curr = get_file_time(curr_m)
            gap = max(0.0, t_curr - t_prev)

            if gap > self.time_gap_threshold_seconds:
                # Salto temporale importante -> Nuovo volo
                flight_groups.append(current_group)
                current_group = [curr_m]
            else:
                # Clip vicina -> Stesso volo (multi-clip)
                current_group.append(curr_m)

        if current_group:
            flight_groups.append(current_group)

        # Costruisci gli oggetti SIVFlight
        from core.timeline_merger import VideoTranscriptionCache, merge_transcriptions_with_offset
        from core.maneuver_detector import ManeuverDetector
        detector = ManeuverDetector()

        siv_flights: List[SIVFlight] = []
        for f_idx, grp in enumerate(flight_groups, start=1):
            clips = []
            caches = []
            for m in grp:
                clip_info = FlightClipInfo(
                    filename=m.filename,
                    video_path=m.video_path,
                    duration=m.duration,
                    start_timestamp=get_file_time(m)
                )
                clips.append(clip_info)
                if m.segments:
                    c = VideoTranscriptionCache(
                        video_path=m.video_path,
                        filename=m.filename,
                        duration=m.duration,
                        segments=m.segments
                    )
                    caches.append(c)

            merged_segments = merge_transcriptions_with_offset(caches) if caches else []
            chapters = detector.detect_chapters(merged_segments) if merged_segments else []

            flight = SIVFlight(
                flight_number=f_idx,
                flight_id=f"Volo_{f_idx:02d}",
                pilot_name=pilot_name,
                clips=clips,
                segments=merged_segments,
                chapters=chapters
            )
            flight.calculate_offsets()
            siv_flights.append(flight)

        return siv_flights
