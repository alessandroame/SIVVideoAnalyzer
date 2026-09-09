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

def extract_keyframe_colors_from_ppm(ppm_bytes: bytes) -> List[Tuple[str, str]]:
    """
    Parsa un'immagine PPM (P6) in memoria e calcola i colori dominanti della vela,
    filtrando automaticamente il colore dominante dello sfondo (lago/cielo se occupa >50% dei pixel).
    """
    if not ppm_bytes.startswith(b"P6"):
        return []

    lines = ppm_bytes.split(b"\n", 3)
    if len(lines) < 4:
        return []

    tokens = ppm_bytes[:100].split()
    if len(tokens) < 4:
        return []

    try:
        width = int(tokens[1])
        height = int(tokens[2])
    except Exception:
        return []

    header_end = ppm_bytes.find(b"\n", ppm_bytes.find(tokens[3])) + 1
    raw_pixels = ppm_bytes[header_end:]

    color_counts: Dict[str, int] = {}
    total_valid = 0
    total_pixels = len(raw_pixels) // 3

    stride = 3
    for i in range(0, len(raw_pixels) - 2, stride):
        r = raw_pixels[i]
        g = raw_pixels[i+1]
        b = raw_pixels[i+2]
        c_name = classify_rgb_color(r, g, b)
        if c_name:
            color_counts[c_name] = color_counts.get(c_name, 0) + 1
            total_valid += 1

    if total_valid < 50:
        return []

    # Rilevamento e rimozione del colore di sfondo massivo:
    # Se il colore dominante (es. Blu del lago) occupa oltre il 35% dell'intera schermata (o oltre il 70% dei pixel validi),
    # è evidentemente lo specchio d'acqua / cielo di sfondo e va filtrato per far emergere i colori della vela.
    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
    top_color, top_count = sorted_colors[0]
    if (top_count / max(1, total_pixels) > 0.30 or top_count / total_valid > 0.65) and top_color in ["Blu", "Ciano"]:
        # Il colore massivo è l'acqua del lago: toglilo dai conteggi
        color_counts.pop(top_color, None)
        total_valid -= top_count

    if total_valid < 30:
        return []

    sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)
    results = []
    for c_name, count in sorted_colors:
        ratio = count / total_valid
        if ratio >= 0.12 and len(results) < 3:
            results.append((c_name, COLOR_PALETTE.get(c_name, "#94a3b8")))

    return results

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
