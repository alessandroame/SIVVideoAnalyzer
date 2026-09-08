import os
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from core.transcriber import TranscriptionSegment
from core.audio_extractor import get_video_duration

@dataclass
class VideoTranscriptionCache:
    video_path: str
    filename: str
    duration: float
    segments: List[TranscriptionSegment]

    def to_dict(self):
        return {
            'video_path': self.video_path,
            'filename': self.filename,
            'duration': self.duration,
            'segments': [asdict(s) for s in self.segments]
        }

    @classmethod
    def from_dict(cls, data: dict):
        segments = [TranscriptionSegment(**s) for s in data.get('segments', [])]
        return cls(
            video_path=data['video_path'],
            filename=data['filename'],
            duration=data.get('duration', 0.0),
            segments=segments
        )

    def save(self, cache_file_path: str):
        os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
        with open(cache_file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, cache_file_path: str) -> Optional['VideoTranscriptionCache']:
        if not os.path.exists(cache_file_path):
            return None
        try:
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception:
            return None

def merge_transcriptions_with_offset(caches: List[VideoTranscriptionCache]) -> List[TranscriptionSegment]:
    merged_segments: List[TranscriptionSegment] = []
    current_time_offset = 0.0

    for item in caches:
        for seg in item.segments:
            shifted = TranscriptionSegment(
                start=seg.start + current_time_offset,
                end=seg.end + current_time_offset,
                text=seg.text
            )
            merged_segments.append(shifted)
        # Incrementa l'offset temporale per il video successivo
        current_time_offset += item.duration

    return merged_segments