import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

class SidecarData:
    """
    Gestore del file sidecar JSON associato a ciascun video:
    - Non tocca mai il file MP4 originale sulla scheda SD
    - Salva e carica istantaneamente i dati (pilota, vela, volo, confidenza, capitoli/manovre)
    - Consente portabilità immediata tra PC diversi e chiavette USB
    """
    def __init__(self, video_path: str):
        self.video_path = os.path.abspath(video_path)
        self.json_path = os.path.splitext(self.video_path)[0] + ".json"
        self.data: Dict[str, Any] = {
            "version": "1.0",
            "source_video": os.path.basename(self.video_path),
            "created_at": datetime.now().isoformat(),
            "metadata": {
                "pilot_name": "",
                "glider": "",
                "flight_number": None,
                "confidence": 0.0,
                "manual_override": False
            },
            "detection_debug": {
                "radio_phrase": "",
                "cameraman_repeat": "",
                "timestamp_voice_start": 0.0
            },
            "chapters": []
        }
        self.load()

    @property
    def radio_phrase(self) -> str:
        return self.data.get("detection_debug", {}).get("radio_phrase", "")

    @radio_phrase.setter
    def radio_phrase(self, value: str):
        if "detection_debug" not in self.data:
            self.data["detection_debug"] = {}
        self.data["detection_debug"]["radio_phrase"] = value

    def exists(self) -> bool:
        return os.path.exists(self.json_path)

    def load(self) -> bool:
        if self.exists():
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
                return True
            except Exception as e:
                print(f"[SidecarData] Errore lettura {self.json_path}: {e}")
        return False

    def save(self) -> bool:
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[SidecarData] Errore scrittura {self.json_path}: {e}")
            return False

    @property
    def pilot_name(self) -> str:
        return self.data["metadata"].get("pilot_name", "")

    @pilot_name.setter
    def pilot_name(self, value: str):
        self.data["metadata"]["pilot_name"] = value.strip()

    @property
    def glider(self) -> str:
        return self.data["metadata"].get("glider", "")

    @glider.setter
    def glider(self, value: str):
        self.data["metadata"]["glider"] = value.strip()

    @property
    def flight_number(self) -> Optional[int]:
        return self.data["metadata"].get("flight_number")

    @flight_number.setter
    def flight_number(self, value: Optional[int]):
        try:
            self.data["metadata"]["flight_number"] = int(value) if value is not None else None
        except (ValueError, TypeError):
            self.data["metadata"]["flight_number"] = None

    @property
    def confidence(self) -> float:
        return float(self.data["metadata"].get("confidence", 0.0))

    @confidence.setter
    def confidence(self, value: float):
        self.data["metadata"]["confidence"] = round(float(value), 2)

    @property
    def manual_override(self) -> bool:
        return bool(self.data["metadata"].get("manual_override", False))

    @manual_override.setter
    def manual_override(self, value: bool):
        self.data["metadata"]["manual_override"] = bool(value)

    @property
    def chapters(self) -> List[Dict[str, Any]]:
        return self.data.get("chapters", [])

    @chapters.setter
    def chapters(self, chapters_list: List[Dict[str, Any]]):
        self.data["chapters"] = chapters_list

    @property
    def recorded_at(self) -> str:
        return self.data["metadata"].get("recorded_at", "")

    @recorded_at.setter
    def recorded_at(self, value: str):
        self.data["metadata"]["recorded_at"] = value.strip()

    @property
    def wing_colors(self) -> List[Dict[str, str]]:
        return self.data.get("metadata", {}).get("wing_colors", [])

    @wing_colors.setter
    def wing_colors(self, colors: List[Dict[str, str]]):
        if "metadata" not in self.data:
            self.data["metadata"] = {}
        self.data["metadata"]["wing_colors"] = colors

    @property
    def audio_confidence(self) -> float:
        return float(self.data.get("metadata", {}).get("audio_confidence", 0.0))

    @audio_confidence.setter
    def audio_confidence(self, value: float):
        if "metadata" not in self.data:
            self.data["metadata"] = {}
        self.data["metadata"]["audio_confidence"] = round(float(value), 2)

    @property
    def wing_confidence(self) -> float:
        return float(self.data.get("metadata", {}).get("wing_confidence", 0.0))

    @wing_confidence.setter
    def wing_confidence(self, value: float):
        if "metadata" not in self.data:
            self.data["metadata"] = {}
        self.data["metadata"]["wing_confidence"] = round(float(value), 2)


    def add_chapter(self, title: str, start: float, end: float, notes: str = "", command: str = ""):
        self.data["chapters"].append({
            "title": title,
            "start": round(start, 2),
            "end": round(end, 2),
            "instructor_command": command,
            "notes": notes
        })
        self.data["chapters"].sort(key=lambda x: x.get("start", 0.0))
        self.save()

    @property
    def tracking(self) -> Optional[Dict[str, Any]]:
        """Restituisce il blocco dati del tracciamento pilota e vela."""
        return self.data.get("tracking")

    @tracking.setter
    def tracking(self, tracking_dict: Optional[Dict[str, Any]]):
        self.data["tracking"] = tracking_dict

    def has_tracking(self) -> bool:
        """Verifica se il file sidecar dispone già dei dati di tracciamento calcolati."""
        tr = self.data.get("tracking")
        return bool(tr and tr.get("trajectory"))

    def get_tracking_boxes_at(self, time_sec: float) -> Tuple[Optional[List[int]], Optional[List[int]]]:
        """
        Ritorna (pilot_box, wing_box) interpolati per il timestamp specificato.
        Ciascun box è espresso in coordinate assolute [x, y, w, h].
        """
        tr = self.data.get("tracking")
        if not tr or not tr.get("trajectory"):
            return None, None
        from core.tracking.smoother import TrajectorySmoother
        return TrajectorySmoother.interpolate_boxes_at(tr["trajectory"], time_sec)

    def add_tracking_keyframe(self, subject: str, t: float, box: List[int]) -> None:
        """Aggiunge o aggiorna un keyframe per pilota o vela, ricalcola la traiettoria e salva il sidecar."""
        tr = self.data.get("tracking")
        if not tr or not tr.get("trajectory"):
            return
        from core.tracking.keyframe_manager import KeyframeManager
        KeyframeManager.add_keyframe(tr, subject, t, box)
        self.save()

    def remove_tracking_keyframe(self, subject: str, t: float, tolerance: float = 0.35) -> bool:
        """Rimuove il keyframe al timestamp specificato, ricalcola la traiettoria e salva il sidecar."""
        tr = self.data.get("tracking")
        if not tr or not tr.get("trajectory"):
            return False
        from core.tracking.keyframe_manager import KeyframeManager
        removed = KeyframeManager.remove_keyframe(tr, subject, t, tolerance=tolerance)
        if removed:
            self.save()
        return removed

    def reset_tracking_keyframes(self) -> None:
        """Ripristina la traiettoria originale AI rimuovendo tutti i ritocchi manuali."""
        tr = self.data.get("tracking")
        if not tr or not tr.get("trajectory"):
            return
        from core.tracking.keyframe_manager import KeyframeManager
        KeyframeManager.reset_keyframes(tr)
        self.save()

    def get_tracking_keyframes(self, subject: Optional[str] = None) -> Any:
        """Restituisce i keyframe manuali del tracciamento."""
        tr = self.data.get("tracking")
        if not tr:
            return [] if subject else {"pilot": [], "wing": []}
        from core.tracking.keyframe_manager import KeyframeManager
        return KeyframeManager.get_keyframes(tr, subject=subject)

