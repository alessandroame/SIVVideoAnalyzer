import os
import shutil
import tempfile
import unittest
from core.manifest_manager import PilotInfo, SivCourseManifest
from core.flight_grouper import FlightGrouper, SIVFlight, FlightClipInfo
from core.pilot_detector import VideoPilotMatch
from core.transcriber import TranscriptionSegment

class TestManifestAndFlights(unittest.TestCase):
    def test_manifest_serialization(self):
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
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "corso_siv_manifest.json")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "Alessandro", "pilota_info.json")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "Marco_Rossi", "pilota_info.json")))

            # Carica
            loaded = SivCourseManifest.load(tmpdir)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.nome_corso, "SIV Malcesine 2026")
            self.assertEqual(len(loaded.piloti), 2)
            self.assertEqual(loaded.piloti[0].vela_marca_modello, "Ozone Rush 6")

    def test_flight_multi_clip_offsets(self):
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
        self.assertEqual(flight.total_duration, 300.0)
        self.assertEqual(flight.clips[0].offset_in_flight, 0.0)
        self.assertEqual(flight.clips[1].offset_in_flight, 180.0)

        # Test get_clip_and_local_time
        c, loc_t = flight.get_clip_and_local_time(50.0)
        self.assertEqual(c.filename, "c1.mp4")
        self.assertEqual(loc_t, 50.0)

        c, loc_t = flight.get_clip_and_local_time(200.0)
        self.assertEqual(c.filename, "c2.mp4")
        self.assertEqual(loc_t, 20.0)

    def test_radio_flight_detection(self):
        from core.pilot_detector import PilotDetector
        detector = PilotDetector(pilots_list=["Mario", "Luigi"])
        
        # Simula segmenti audio con chiamata "Mario, secondo volo"
        segments = [
            TranscriptionSegment(start=1.0, end=4.0, text="Ok Mario mi ricevi, pronto per il secondo volo?"),
            TranscriptionSegment(start=5.0, end=8.0, text="Fai un beccheggio e poi asimmetrica")
        ]
        match = detector.match_pilot_from_segments("dummy.mp4", segments)
        self.assertEqual(match.detected_pilot, "Mario")
        self.assertEqual(match.flight_number, 2)

        # Chiamata con "primo volo"
        segments_1 = [
            TranscriptionSegment(start=1.0, end=4.0, text="Luigi volo uno, chiudi la destra")
        ]
        match_1 = detector.match_pilot_from_segments("dummy2.mp4", segments_1)
        self.assertEqual(match_1.detected_pilot, "Luigi")
        self.assertEqual(match_1.flight_number, 1)

    def test_flight_grouper_with_radio_flights(self):
        grouper = FlightGrouper(time_gap_threshold_seconds=1200.0)
        
        matches = [
            VideoPilotMatch(video_path="/v1.mp4", filename="v1.mp4", detected_pilot="Mario", confidence=1.0, matched_phrases=[], duration=100.0, flight_number=1),
            VideoPilotMatch(video_path="/v2.mp4", filename="v2.mp4", detected_pilot="Mario", confidence=1.0, matched_phrases=[], duration=120.0, flight_number=1),
            VideoPilotMatch(video_path="/v3.mp4", filename="v3.mp4", detected_pilot="Mario", confidence=1.0, matched_phrases=[], duration=150.0, flight_number=2)
        ]
        flights = grouper.group_pilot_matches_into_flights("Mario", matches)
        self.assertEqual(len(flights), 2)
        self.assertEqual(flights[0].flight_number, 1)
        self.assertEqual(len(flights[0].clips), 2)
        self.assertEqual(flights[1].flight_number, 2)
        self.assertEqual(len(flights[1].clips), 1)

    def test_maneuver_worker_progress(self):
        from ui.maneuver_worker import ManeuverCalculationWorker
        from unittest.mock import MagicMock
        from core.transcriber import TranscriptionSegment
        from core.sidecar_manager import SidecarData
        from core.pilot_detector import VideoTranscriptionCache

        with tempfile.TemporaryDirectory() as tmpdir:
            test_mp4 = os.path.join(tmpdir, "test_clip.mp4")
            with open(test_mp4, "wb") as f:
                f.write(b"fake_mp4_bytes")

            # Crea cache fittizia
            os.makedirs("temp", exist_ok=True)
            cache_file = os.path.join("temp", "test_clip_cache.json")
            cache_data = VideoTranscriptionCache(
                video_path=test_mp4,
                filename="test_clip.mp4",
                duration=30.0,
                segments=[
                    TranscriptionSegment(start=2.0, end=6.0, text="Ok chiudi asimmetrica a destra tieni l'appoggio")
                ]
            )
            cache_data.save(cache_file)

            worker = ManeuverCalculationWorker(
                video_path=test_mp4,
                transcriber=MagicMock(),
                maneuver_detector=None,
                pilot_names=["Test Pilot"]
            )

            progress_events = []
            worker.progress_update.connect(lambda vp, txt, pct: progress_events.append((vp, txt, pct)))

            results = []
            worker.maneuvers_ready.connect(lambda vp, chs: results.append((vp, chs)))

            worker.run()

            # Pulisci cache creata
            if os.path.exists(cache_file):
                os.remove(cache_file)

            self.assertTrue(len(progress_events) >= 2)
            self.assertEqual(progress_events[-1][2], 100)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0], test_mp4)
            self.assertTrue(len(results[0][1]) >= 1)
            self.assertIn("Asimmetrica", results[0][1][0]["title"])
