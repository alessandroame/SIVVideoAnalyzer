import unittest
from core.pilot_detector import parse_pilots_text

class TestPilotParser(unittest.TestCase):
    def test_multiline_standard(self):
        text = "Alessandro - Rosso / Giallo\nAndrea - Bianco / Rosso"
        result = parse_pilots_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("Alessandro", "Rosso / Giallo"))
        self.assertEqual(result[1], ("Andrea", "Bianco / Rosso"))

    def test_single_line_comma_with_dashes(self):
        text = "alessandro - rosso / giallo, andrea - bianco / rosso"
        result = parse_pilots_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("Alessandro", "rosso / giallo"))
        self.assertEqual(result[1], ("Andrea", "bianco / rosso"))

    def test_single_line_trailing_colors_without_dash(self):
        text = "alessandro - rosso / giallo, andrea bianco / rosso"
        result = parse_pilots_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("Alessandro", "rosso / giallo"))
        self.assertEqual(result[1], ("Andrea", "bianco / rosso"))

    def test_single_line_semicolon(self):
        text = "Alessandro - Rosso / Giallo; Andrea - Bianco / Rosso"
        result = parse_pilots_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("Alessandro", "Rosso / Giallo"))
        self.assertEqual(result[1], ("Andrea", "Bianco / Rosso"))

    def test_only_names_comma_separated(self):
        text = "Alessandro, Andrea, Marco Rossi"
        result = parse_pilots_text(text)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("Alessandro", ""))
        self.assertEqual(result[1], ("Andrea", ""))
        self.assertEqual(result[2], ("Marco Rossi", ""))

    def test_multiple_colors_single_pilot(self):
        # La virgola qui separa i colori della vela dello stesso pilota, non due piloti
        text = "Alessandro - Rosso, Giallo\nAndrea - Bianco, Rosso"
        result = parse_pilots_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("Alessandro", "Rosso, Giallo"))
        self.assertEqual(result[1], ("Andrea", "Bianco, Rosso"))

    def test_parentheses_and_numbered(self):
        text = "1. Alessandro (Rosso / Giallo)\n2. Andrea (Bianco / Rosso)"
        result = parse_pilots_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("Alessandro", "Rosso / Giallo"))
        self.assertEqual(result[1], ("Andrea", "Bianco / Rosso"))

    def test_case_insensitive_deduplication(self):
        text = "Alessandro - Rosso\nalessandro - Giallo"
        result = parse_pilots_text(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "Alessandro")

    def test_empty_input(self):
        self.assertEqual(parse_pilots_text(""), [])
        self.assertEqual(parse_pilots_text("   \n\n  "), [])

if __name__ == "__main__":
    unittest.main()
