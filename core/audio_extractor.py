import os
import subprocess
from pathlib import Path
import imageio_ffmpeg

def get_ffmpeg_binary() -> str:
    """Restituisce il percorso dell'eseguibile ffmpeg incorporato."""
    return imageio_ffmpeg.get_ffmpeg_exe()

def extract_audio(video_path: str, output_wav_path: str, sample_rate: int = 16000) -> str:
    """
    Estrae l'audio da un video in formato WAV mono 16kHz ottimizzato per Whisper.
    Applica filtri per:
    1. Tagliare le basse frequenze del vento (< 200 Hz)
    2. Tagliare i fischi e disturbi ad alta frequenza (> 3500 Hz)
    3. Normalizzare il volume della radio (loudnorm)
    """
    ffmpeg_exe = get_ffmpeg_binary()
    os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)
    
    # Filtro audio passa-banda per voce radio + soppressione vento + normalizzazione volume
    audio_filter = "highpass=f=200,lowpass=f=3500,loudnorm=I=-16:TP=-1.5:LRA=11"

    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-af", audio_filter,
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",
        str(output_wav_path)
    ]
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Errore estrazione audio con ffmpeg: {result.stderr}")
        
    return output_wav_path

def get_video_duration(video_path: str) -> float:
    """Calcola la durata in secondi di un video/audio tramite ffmpeg."""
    ffmpeg_exe = get_ffmpeg_binary()
    cmd = [
        ffmpeg_exe,
        "-i", str(video_path),
        "-hide_banner"
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Cerca la stringa 'Duration: 00:01:23.45'
    import re
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
    if match:
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return 0.0

def get_video_creation_time(video_path: str) -> float:
    """
    Estrae il timestamp di creazione originale (Unix epoch) dai metadati del file (es. QuickTime/MP4 creation_time).
    Se assente o invalido, ricade sul timestamp del filesystem (os.path.getmtime).
    """
    import datetime
    import re
    
    ffmpeg_exe = get_ffmpeg_binary()
    cmd = [
        ffmpeg_exe,
        "-i", str(video_path),
        "-hide_banner"
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Cerca creation_time nei metadati: es. "creation_time   : 2026-05-14T09:30:15.000000Z"
        match = re.search(r"creation_time\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z?)", result.stderr, re.IGNORECASE)
        if match:
            dt_str = match.group(1).replace("Z", "").replace("T", " ")
            # Se ha frazioni di secondo, prendi solo i primi 19 caratteri YYYY-MM-DD HH:MM:SS
            dt_clean = dt_str[:19]
            dt = datetime.datetime.strptime(dt_clean, "%Y-%m-%d %H:%M:%S")
            return dt.timestamp()
    except Exception:
        pass

    # Fallback: filesystem mtime
    try:
        return os.path.getmtime(video_path)
    except Exception:
        return 0.0
