import os
import subprocess
import colorsys
from typing import List, Dict, Tuple, Optional
from thefuzz import fuzz
from core.audio_extractor import get_ffmpeg_binary, get_video_duration

COLOR_PALETTE = {
    "Rosso": "#ef4444",
    "Arancione": "#f97316",
    "Giallo": "#eab308",
    "Verde": "#22c55e",
    "Lime": "#84cc16",
    "Ciano": "#06b6d4",
    "Blu": "#3b82f6",
    "Viola": "#a855f7",
    "Rosa": "#ec4899",
    "Bianco": "#f8fafc",
    "Nero": "#0f172a",
}

def classify_rgb_color(r: int, g: int, b: int) -> Optional[str]:
    """
    Classifica un pixel RGB in una categoria di colore della vela,
    filtrando sfondi tipici del lago e cielo se poco saturi o a toni neutri.
    """
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    h, s, v = colorsys.rgb_to_hsv(rf, gf, bf)
    h_deg = h * 360.0

    # Nero / Porzioni scure della vela
    if v < 0.25 and s < 0.30:
        if v >= 0.05:
            return "Nero"
        return None

    # Troppo scuro (rumore sensore camera)
    if v < 0.15:
        return None

    # Troppo desaturo / neutro (cielo nuvoloso, foschia, lago opaco)
    if s < 0.20:
        if v > 0.85:
            return "Bianco"
        return None  # Grigio/sfondo ignorato

    # Filtra il cielo azzurro di sfondo standard (tonalità ciano/blu tenue desaturato)
    if (195 <= h_deg <= 235) and s < 0.45 and v > 0.55:
        return None

    # Classificazione colori saturi della vela
    if h_deg < 20 or h_deg >= 340:
        return "Rosso"
    elif h_deg < 45:
        return "Arancione"
    elif h_deg < 72:
        return "Giallo"
    elif h_deg < 95:
        return "Lime"
    elif h_deg < 165:
        return "Verde"
    elif h_deg < 195:
        return "Ciano"
    elif h_deg < 255:
        return "Blu"
    elif h_deg < 290:
        return "Viola"
    elif h_deg < 340:
        return "Rosa"

    return None

import numpy as np

def segment_wing_from_ppm(ppm_bytes: bytes) -> Tuple[Optional[bytes], List[Tuple[str, str]], int, int, int]:
    """
    Segmenta la vela dallo sfondo (cielo / lago / paesaggio) usando numpy vettoriale.
    Ritorna:
        isolated_ppm_bytes: Immagine PPM con SOLI i pixel della vela (sfondo nero #000000).
        colors: Lista di colori dominanti della vela [(nome, hex), ...].
        wing_pixel_count: Numero di pixel appartenenti alla vela.
        width: Larghezza immagine.
        height: Altezza immagine.
    """
    if not ppm_bytes.startswith(b"P6"):
        return None, [], 0, 0, 0

    tokens = ppm_bytes[:100].split()
    if len(tokens) < 4:
        return None, [], 0, 0, 0

    try:
        width = int(tokens[1])
        height = int(tokens[2])
    except Exception:
        return None, [], 0, 0, 0

    header_end = ppm_bytes.find(b"\n", ppm_bytes.find(tokens[3])) + 1
    raw_pixels = ppm_bytes[header_end:]
    expected_len = width * height * 3
    if len(raw_pixels) < expected_len:
        return None, [], 0, width, height

    # Carica in array numpy uint8 (H, W, 3)
    img = np.frombuffer(raw_pixels[:expected_len], dtype=np.uint8).reshape((height, width, 3))

    # Conversione vettoriale RGB -> HSV normalizzato (H: 0-360, S: 0-1, V: 0-1)
    rgb_f = img.astype(np.float32) / 255.0
    r = rgb_f[:, :, 0]
    g = rgb_f[:, :, 1]
    b = rgb_f[:, :, 2]

    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin

    # Calcolo Hue
    h_deg = np.zeros_like(r)
    nonzero = delta > 1e-5
    idx_r = nonzero & (cmax == r)
    idx_g = nonzero & (cmax == g)
    idx_b = nonzero & (cmax == b)

    h_deg[idx_r] = (60.0 * ((g[idx_r] - b[idx_r]) / delta[idx_r])) % 360.0
    h_deg[idx_g] = (60.0 * ((b[idx_g] - r[idx_g]) / delta[idx_g])) + 120.0
    h_deg[idx_b] = (60.0 * ((r[idx_b] - g[idx_b]) / delta[idx_b])) + 240.0

    # Calcolo Saturation & Value
    s = np.zeros_like(r)
    s[cmax > 1e-5] = delta[cmax > 1e-5] / cmax[cmax > 1e-5]
    v = cmax

    # -------------------------------------------------------------
    # FILTRO AVANZATO: Distinzione Vela vs Sfondo (Cielo, Lago, Montagna)
    # -------------------------------------------------------------
    # 1. Cielo standard (azzurro / celeste uniforme desaturo)
    sky_mask = (h_deg >= 195) & (h_deg <= 240) & (s < 0.50) & (v > 0.45)

    # 2. Sfondo lago e ombre dell'acqua (toni spenti, grigi, o ciano/blu-grigio a bassa saturazione)
    water_haze_mask = (s < 0.22) & (v < 0.85) & (v > 0.25)
    too_dark_noise = (v < 0.12)

    # 3. Pixel ad ALTA SATURAZIONE (caratteristici dei tessuti di parapendio: rosso, arancio, giallo, lime, viola, ciano saturo, ecc.)
    vibrant_wing_colors = (s >= 0.25) & (v >= 0.18) & (~sky_mask)

    # 4. Pixel NERI o BIANCHI della vela:
    # Vengono considerati parte della vela se sono contrastati ma non rumore di fondo
    wing_white = (s < 0.20) & (v >= 0.85)
    wing_black = (s < 0.30) & (v >= 0.05) & (v < 0.25)

    # Maschera preliminare di candidati vela (il nero non è rumore troppo scuro)
    raw_wing_mask = vibrant_wing_colors | wing_white | wing_black
    raw_wing_mask = raw_wing_mask & (~water_haze_mask) & (v >= 0.05)

    # Rileva se un colore dominante di sfondo (es. lago esteso) è penetrato nella maschera
    # Se un cluster di pixel ciano/blu o verde-grigio occupa più del 35% del frame totale, è lo specchio d'acqua
    blue_lake = (h_deg >= 180) & (h_deg <= 245) & (s < 0.65)
    if np.sum(blue_lake) > (width * height * 0.30):
        raw_wing_mask = raw_wing_mask & (~blue_lake)

    wing_pixel_count = int(np.sum(raw_wing_mask))

    # Genera immagine isolata: azzera completamente lo sfondo
    isolated_img = np.zeros_like(img)
    isolated_img[raw_wing_mask] = img[raw_wing_mask]

    # Ricostruisci buffer PPM P6 dell'immagine isolata
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    isolated_ppm_bytes = header + isolated_img.tobytes()

    # Se ci sono troppo pochi pixel di vela rilevati (meno di 15 px o meno dello 0.05% dell'immagine)
    min_pixels = max(10, int(width * height * 0.0005))
    if wing_pixel_count < min_pixels:
        return isolated_ppm_bytes, [], wing_pixel_count, width, height

    # -------------------------------------------------------------
    # Classificazione colori ESCLUSIVAMENTE sui pixel isolati della vela
    # -------------------------------------------------------------
    wing_r = img[:, :, 0][raw_wing_mask]
    wing_g = img[:, :, 1][raw_wing_mask]
    wing_b = img[:, :, 2][raw_wing_mask]

    color_counts: Dict[str, int] = {}
    stride = max(1, len(wing_r) // 1000)  # Campiona fino a 1000 pixel significativi
    for i in range(0, len(wing_r), stride):
        c_name = classify_rgb_color(int(wing_r[i]), int(wing_g[i]), int(wing_b[i]))
        if c_name:
            color_counts[c_name] = color_counts.get(c_name, 0) + 1

    total_valid = sum(color_counts.values())
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
    results = []
    for c_name, count in sorted_colors:
        ratio = count / max(1, total_valid)
        if ratio >= 0.12 and len(results) < 3:
            results.append((c_name, COLOR_PALETTE.get(c_name, "#94a3b8")))

    return isolated_ppm_bytes, results, wing_pixel_count, width, height

def extract_keyframe_colors_from_ppm(ppm_bytes: bytes) -> List[Tuple[str, str]]:
    """
    Parsa un'immagine PPM (P6) in memoria e calcola i colori dominanti della vela,
    usando la segmentazione e isolamento dello sfondo.
    """
    _, colors, _, _, _ = segment_wing_from_ppm(ppm_bytes)
    return colors

def detect_wing_colors_from_video(video_path: str, duration: float = 0.0) -> List[Tuple[str, str]]:
    """
    Estrae 2 frame a 25% e 50% durata, estrae i colori e aggrega i dominanti.
    """
    if not os.path.exists(video_path):
        return []

    ffmpeg_exe = get_ffmpeg_binary()
    if duration <= 0:
        duration = get_video_duration(video_path)

    if duration <= 0:
        duration = 10.0

    sample_timestamps = [duration * 0.20, duration * 0.40, duration * 0.65]
    aggregated_colors: Dict[str, int] = {}

    for ts in sample_timestamps:
        cmd = [
            ffmpeg_exe,
            "-ss", str(round(ts, 2)),
            "-i", str(video_path),
            "-vframes", "1",
            "-s", "320x180",
            "-f", "image2pipe",
            "-vcodec", "ppm",
            "-"
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
            if res.returncode == 0 and res.stdout:
                cols = extract_keyframe_colors_from_ppm(res.stdout)
                for c_name, _ in cols:
                    aggregated_colors[c_name] = aggregated_colors.get(c_name, 0) + 1
        except Exception:
            pass

    results = []
    for c_name, _ in sorted(aggregated_colors.items(), key=lambda x: x[1], reverse=True):
        if len(results) < 3:
            results.append((c_name, COLOR_PALETTE.get(c_name, "#94a3b8")))
    return results

def match_detected_colors_to_pilots(detected_colors: List[Tuple[str, str]], pilot_gliders: Dict[str, str]) -> Optional[Tuple[str, float]]:
    """
    Confronta i colori rilevati con le descrizioni delle vele dei piloti.
    pilot_gliders: { 'mario rossi': 'Rosso/Nero', 'luca bianchi': 'Lime/Bianco' }
    Ritorna (nome_pilota, score_confidenza) o None.
    """
    if not detected_colors or not pilot_gliders:
        return None

    det_names = [c[0].lower() for c in detected_colors]
    best_pilot = None
    best_score = 0.0

    for pilot_name, glider_desc in pilot_gliders.items():
        if not glider_desc:
            continue
        g_lower = glider_desc.lower()
        matches = 0
        for d in det_names:
            if d in g_lower:
                matches += 1
            elif d == "lime" and ("verde" in g_lower or "lime" in g_lower):
                matches += 1
            elif d == "arancione" and "orange" in g_lower:
                matches += 1

        if matches > 0:
            score = matches / max(1, len(det_names))
            if score > best_score:
                best_score = score
                best_pilot = pilot_name

    if best_pilot and best_score >= 0.5:
        # Confidenza indicativa tra 0.65 e 0.75 per suggerimento visivo
        return (best_pilot, min(0.75, 0.55 + best_score * 0.20))

    return None
