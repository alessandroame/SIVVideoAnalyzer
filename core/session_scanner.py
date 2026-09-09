import os
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple
from core.audio_extractor import get_video_creation_time
from core.sidecar_manager import SidecarData

VALID_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".mts", ".m2ts"}

@dataclass
class SessionScanResult:
    folder_path: str
    total_videos: int = 0
    all_videos: List[str] = field(default_factory=list)
    analyzed_videos: List[str] = field(default_factory=list)
    pending_videos: List[str] = field(default_factory=list)
    cached_videos: List[str] = field(default_factory=list)
    discovered_pilots: Dict[str, str] = field(default_factory=dict)

    @property
    def is_fully_analyzed(self) -> bool:
        return self.total_videos > 0 and len(self.analyzed_videos) == self.total_videos

    @property
    def has_any_analyzed(self) -> bool:
        return len(self.analyzed_videos) > 0

def scan_session_folder(folder_path: str) -> SessionScanResult:
    res = SessionScanResult(folder_path=folder_path)
    if not folder_path or not os.path.exists(folder_path):
        return res

    video_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if os.path.splitext(file)[1].lower() in VALID_VIDEO_EXTENSIONS:
                video_files.append(os.path.join(root, file))

    if not video_files:
        return res

    try:
        sorted_videos = sorted(
            list(set(video_files)),
            key=lambda vf: (get_video_creation_time(vf), os.path.basename(vf).lower())
        )
    except Exception:
        sorted_videos = sorted(list(set(video_files)))

    res.total_videos = len(sorted_videos)
    res.all_videos = sorted_videos

    temp_cache_dir = "temp"

    for vf in sorted_videos:
        sc = SidecarData(vf)
        base_name = os.path.splitext(os.path.basename(vf))[0]
        cache_path = os.path.join(temp_cache_dir, f"{base_name}_cache.json")

        has_cache = os.path.exists(cache_path)
        if has_cache:
            res.cached_videos.append(vf)

        if sc.pilot_name and sc.pilot_name not in ["In attesa...", "Da Assegnare"]:
            res.analyzed_videos.append(vf)
            p_clean = sc.pilot_name.strip()
            g_clean = sc.glider.strip() if sc.glider else ""
            if p_clean and p_clean not in res.discovered_pilots:
                res.discovered_pilots[p_clean] = g_clean
            elif p_clean and g_clean and not res.discovered_pilots.get(p_clean):
                res.discovered_pilots[p_clean] = g_clean
        else:
            res.pending_videos.append(vf)

    return res
