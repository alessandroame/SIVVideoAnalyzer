import unittest
from core.transcriber import TranscriptionSegment
from core.maneuver_detector import ManeuverDetector, SIVChapter
from core.pilot_detector import PilotDetector

class TestCore(unittest.TestCase):
    def test_maneuver_detection(self):
        detector = ManeuverDetector()
        segments = [
            TranscriptionSegment(start=10.0, end=14.0, text="Ok Marco sei in box, prova una chiusura asimmetrica a destra"),
            TranscriptionSegment(start=25.0, end=28.0, text="Bravo, rilascia e lascia volare"),
            TranscriptionSegment(start=45.0, end=50.0, text="Adesso prepariamo un full stall, tutto giù i freni deciso"),
            TranscriptionSegment(start=80.0, end=85.0, text="Fai le grandi orecchie con acceleratore")
        ]
        
        chapters = detector.detect_chapters(segments, min_score=70)
        self.assertGreaterEqual(len(chapters), 3)
        
        maneuver_names = [ch.maneuver_name for ch in chapters]
        self.assertTrue(any("Asimmetrica Destra" in name for name in maneuver_names))
        self.assertTrue(any("Full Stall" in name for name in maneuver_names))
        self.assertTrue(any("Orecchie" in name for name in maneuver_names))

    def test_repeat_phrases_detection(self):
        """Verifica che frasi come 'fanne un'altra', 'riproviamo' generino un nuovo capitolo ereditando la manovra precedente."""
        detector = ManeuverDetector()
        segments = [
            TranscriptionSegment(start=10.0, end=14.0, text="Alessandro pronto, prova una chiusura asimmetrica a destra"),
            TranscriptionSegment(start=20.0, end=24.0, text="Bravo, controlla il beccheggio e lascia volare"),
            # Comando di ripetizione della stessa manovra
            TranscriptionSegment(start=35.0, end=39.0, text="Molto bene, fanne un'altra subito"),
            TranscriptionSegment(start=40.0, end=42.0, text="3, 2, 1, tira deciso!")
        ]

        chapters = detector.detect_chapters(segments, min_score=70)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0].maneuver_id, "asimmetrica_destra")
        self.assertEqual(chapters[1].maneuver_id, "asimmetrica_destra")
        self.assertGreater(chapters[1].start_time, chapters[0].start_time)
        # Il secondo capitolo deve aver agganciato il comando esecutivo 3, 2, 1 tira deciso
        self.assertEqual(chapters[1].start_time, 40.0)

    def test_repeat_phrases_riproviamo(self):
        """Verifica anche 'riproviamo la stessa' o 'ancora una'."""
        detector = ManeuverDetector()
        segments = [
            TranscriptionSegment(start=10.0, end=14.0, text="Prepariamo una bella chiusura frontale"),
            TranscriptionSegment(start=15.0, end=17.0, text="Tira le due A deciso!"),
            TranscriptionSegment(start=28.0, end=30.0, text="Lascia scorrere"),
            TranscriptionSegment(start=35.0, end=38.0, text="Riproviamo, ancora una volta!"),
            TranscriptionSegment(start=39.0, end=41.0, text="Vai, tira!")
        ]

        chapters = detector.detect_chapters(segments, min_score=70)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0].maneuver_id, "frontale")
        self.assertEqual(chapters[1].maneuver_id, "frontale")

    def test_custom_maneuvers_filtering(self):
        """Verifica che disabilitare manovre ne impedisca il rilevamento."""
        detector = ManeuverDetector()
        # Abilita solo asimmetrica destra, escludi frontale
        detector.enabled_maneuver_ids = {"asimmetrica_destra"}

        segments = [
            TranscriptionSegment(start=10.0, end=14.0, text="Prova una chiusura asimmetrica a destra"),
            TranscriptionSegment(start=30.0, end=34.0, text="Adesso prepariamo una frontale")
        ]

        chapters = detector.detect_chapters(segments, min_score=70)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].maneuver_id, "asimmetrica_destra")

    def test_pilot_detection_from_segments(self):
        detector = PilotDetector(pilots_list=["Marco Rossi", "Luca Bianchi", "Giulia Verdi"])
        segments = [
            TranscriptionSegment(start=2.0, end=5.0, text="Radio check, Marco mi ricevi forte e chiaro?"),
            TranscriptionSegment(start=6.0, end=8.0, text="Ok Marco Rossi pronto per il lancio")
        ]
        match = detector.match_pilot_from_segments("GX010042.MP4", segments)
        self.assertEqual(match.detected_pilot, "Marco Rossi")
        self.assertGreaterEqual(match.confidence, 0.5)
