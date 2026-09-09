import pytest
from core.wing_color_detector import (
    classify_rgb_color,
    extract_keyframe_colors_from_ppm,
    match_detected_colors_to_pilots
)

def test_classify_rgb_color():
    # Rosso saturo
    assert classify_rgb_color(255, 0, 0) == "Rosso"
    # Giallo saturo
    assert classify_rgb_color(255, 255, 0) == "Giallo"
    # Lime
    assert classify_rgb_color(160, 240, 20) == "Lime"
    # Blu saturo
    assert classify_rgb_color(0, 50, 255) == "Blu"
    # Nero profondo
    assert classify_rgb_color(20, 20, 20) == "Nero"
    # Bianco brillante
    assert classify_rgb_color(250, 250, 250) == "Bianco"
    # Grigio/cielo desaturo ignorato
    assert classify_rgb_color(150, 150, 150) is None
    # Cielo azzurro standard filtrato
    assert classify_rgb_color(160, 210, 240) is None

def test_extract_keyframe_colors_from_ppm():
    # Crea un header PPM valido 10x10 con pixel rossi e neri
    w, h = 10, 10
    header = f"P6\n{w} {h}\n255\n".encode("ascii")
    # 60 pixel rossi, 40 pixel neri
    red_pix = bytes([255, 0, 0] * 60)
    black_pix = bytes([20, 20, 20] * 40)
    ppm_data = header + red_pix + black_pix

    res = extract_keyframe_colors_from_ppm(ppm_data)
    color_names = [r[0] for r in res]
    assert "Rosso" in color_names
    assert "Nero" in color_names

def test_match_detected_colors_to_pilots():
    pilot_gliders = {
        "Mario Rossi": "Rosso/Nero",
        "Luca Bianchi": "Blu/Bianco",
        "Alessandro": "Lime/Nero"
    }

    detected = [("Rosso", "#ef4444"), ("Nero", "#0f172a")]
    match = match_detected_colors_to_pilots(detected, pilot_gliders)
    assert match is not None
    pilot, conf = match
    assert pilot == "Mario Rossi"
    assert 0.60 <= conf <= 0.80

    detected_lime = [("Lime", "#84cc16")]
    match_lime = match_detected_colors_to_pilots(detected_lime, pilot_gliders)
    assert match_lime is not None
    assert match_lime[0] == "Alessandro"

def test_segment_wing_from_ppm():
    from core.wing_color_detector import segment_wing_from_ppm
    # Immagine 10x10: 80 pixel azzurri (cielo/lago), 20 pixel arancioni saturi (vela)
    w, h = 10, 10
    header = f"P6\n{w} {h}\n255\n".encode("ascii")
    # Cielo azzurro desaturo: R=160, G=210, B=240
    sky_pix = bytes([160, 210, 240] * 80)
    # Vela arancione satura: R=255, G=110, B=20
    wing_pix = bytes([255, 110, 20] * 20)
    ppm_data = header + sky_pix + wing_pix

    iso_ppm, colors, wing_count, out_w, out_h = segment_wing_from_ppm(ppm_data)
    assert iso_ppm is not None
    assert out_w == 10 and out_h == 10
    # La vela deve essere isolata (20 pixel circa)
    assert wing_count == 20
    color_names = [c[0] for c in colors]
    assert "Arancione" in color_names

