import pytest
from core.transcriber import TranscriptionSegment
from core.maneuver_detector import ManeuverDetector, SIVChapter
from core.pilot_detector import PilotDetector

def test_maneuver_detection():
    detector = ManeuverDetector()
    segments = [
        TranscriptionSegment(start=10.0, end=14.0, text="Ok Marco sei in box, prova una chiusura asimmetrica a destra"),
        TranscriptionSegment(start=25.0, end=28.0, text="Bravo, rilascia e lascia volare"),
        TranscriptionSegment(start=45.0, end=50.0, text="Adesso prepariamo un full stall, tutto giù i freni deciso"),
        TranscriptionSegment(start=80.0, end=85.0, text="Fai le grandi orecchie con acceleratore")
    ]
    
    chapters = detector.detect_chapters(segments, min_score=70)
    assert len(chapters) >= 3
    
    maneuver_names = [ch.maneuver_name for ch in chapters]
    assert any("Asimmetrica Destra" in name for name in maneuver_names)
    assert any("Full Stall" in name for name in maneuver_names)
    assert any("Orecchie" in name for name in maneuver_names)

def test_pilot_detection_from_segments():
    detector = PilotDetector(pilots_list=["Marco Rossi", "Luca Bianchi", "Giulia Verdi"])
    segments = [
        TranscriptionSegment(start=2.0, end=5.0, text="Radio check, Marco mi ricevi forte e chiaro?"),
        TranscriptionSegment(start=6.0, end=8.0, text="Ok Marco Rossi pronto per il lancio")
    ]
    match = detector.match_pilot_from_segments("GX010042.MP4", segments)
    assert match.detected_pilot == "Marco Rossi"
    assert match.confidence >= 0.5
