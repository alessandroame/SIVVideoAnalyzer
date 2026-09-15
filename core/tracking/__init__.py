"""
Package per il tracciamento automatico di Pilota e Vela per il debriefing SIV.
Include rilevamento cromatico, fisica pendolare, smoothing cinematografico e pipeline video.
"""

from core.tracking.wing_tracker import WingTracker, WingBox
from core.tracking.pilot_tracker import PilotTracker, PilotBox
from core.tracking.smoother import TrajectorySmoother
from core.tracking.pipeline import VideoTrackingPipeline

__all__ = [
    "WingTracker",
    "WingBox",
    "PilotTracker",
    "PilotBox",
    "TrajectorySmoother",
    "VideoTrackingPipeline",
]
