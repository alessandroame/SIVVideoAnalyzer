import os
import shutil
import tempfile
import pytest
from core.manifest_manager import PilotInfo, SivCourseManifest
from core.flight_grouper import FlightGrouper, SIVFlight, FlightClipInfo
from core.pilot_detector import VideoPilotMatch
from core.transcriber import TranscriptionSegment

def test_manifest_serialization():
    with tempfile.TemporaryDirectory() as tmpdir:
        pilots = [
            PilotInfo(id="ale", nome="Alessandro", vela_marca_modello="Ozone Rush 6", colori_vela="Rosso/Nero"),
            PilotInfo(id="marco", nome="Marco Rossi", vela_marca_modello="Advance Iota DLS", colori_vela="Verde/Lime")
        ]
        manifest = SivCourseManifest(
            nome_corso="SIV Malcesine 2026",
            istruttore="Istruttore SIV",
            piloti=pilots
        )
        manifest.save(tmpdir)

        # Verifica file
        assert os.path.exists(os.path.join(tmpdir, "corso_siv_manifest.json"))
        assert os.path.exists(os.path.join(tmpdir, "Alessandro", "pilota_info.json"))
        assert os.path.exists(os.path.join(tmpdir, "Marco_Rossi", "pilota_info.json"))

        # Carica
        loaded = SivCourseManifest.load(tmpdir)
        assert loaded is not None
        assert loaded.nome_corso == "SIV Malcesine 2026"
        assert len(loaded.piloti) == 2
        assert loaded.piloti[0].vela_marca_modello == "Ozone Rush 6"

def test_flight_multi_clip_offsets():
    flight = SIVFlight(
        flight_number=1,
        flight_id="Volo_01",
        pilot_name="Alessandro",
        clips=[
            FlightClipInfo(filename="c1.mp4", video_path="/c1.mp4", duration=180.0),
            FlightClipInfo(filename="c2.mp4", video_path="/c2.mp4", duration=120.0)
        ]
    )
    flight.calculate_offsets()
    assert flight.total_duration == 300.0
    assert flight.clips[0].offset_in_flight == 0.0
    assert flight.clips[1].offset_in_flight == 180.0

    # Test get_clip_and_local_time
    c, loc_t = flight.get_clip_and_local_time(50.0)
    assert c.filename == "c1.mp4"
    assert loc_t == 50.0

    c, loc_t = flight.get_clip_and_local_time(200.0)
    assert c.filename == "c2.mp4"
    assert loc_t == 20.0  # 200 - 180

def test_radio_flight_detection():
    from core.pilot_detector import PilotDetector
    detector = PilotDetector(pilots_list=["Mario", "Luigi"])
    
    # Simula segmenti audio con chiamata "Mario, secondo volo"
    segments = [
        TranscriptionSegment(start=1.0, end=4.0, text="Ok Mario mi ricevi, pronto per il secondo volo?"),
        TranscriptionSegment(start=5.0, end=8.0, text="Fai un beccheggio e poi asimmetrica")
    ]
    match = detector.match_pilot_from_segments("dummy.mp4", segments)
    assert match.detected_pilot == "Mario"
    assert match.flight_number == 2

    # Chiamata con "primo volo"
    segments_1 = [
        TranscriptionSegment(start=1.0, end=4.0, text="Luigi volo uno, chiudi la destra")
    ]
    match_1 = detector.match_pilot_from_segments("dummy2.mp4", segments_1)
    assert match_1.detected_pilot == "Luigi"
    assert match_1.flight_number == 1

def test_flight_grouper_with_radio_flights():
    grouper = FlightGrouper(time_gap_threshold_seconds=1200.0)
    
    matches = [
        VideoPilotMatch(video_path="/v1.mp4", filename="v1.mp4", detected_pilot="Mario", confidence=1.0, matched_phrases=[], duration=100.0, flight_number=1),
        VideoPilotMatch(video_path="/v2.mp4", filename="v2.mp4", detected_pilot="Mario", confidence=1.0, matched_phrases=[], duration=120.0, flight_number=1),
        VideoPilotMatch(video_path="/v3.mp4", filename="v3.mp4", detected_pilot="Mario", confidence=1.0, matched_phrases=[], duration=150.0, flight_number=2)
    ]
    flights = grouper.group_pilot_matches_into_flights("Mario", matches)
    assert len(flights) == 2
    assert flights[0].flight_number == 1
    assert len(flights[0].clips) == 2
    assert flights[1].flight_number == 2
    assert len(flights[1].clips) == 1
