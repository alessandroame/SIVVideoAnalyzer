import os
import subprocess
from pathlib import Path
import imageio_ffmpeg

def get_ffmpeg_binary() -> str:
    """Restituisce il percorso dell'eseguibile ffmpeg incorporato."""
    return imageio_ffmpeg.get_ffmpeg_exe()

def extract_audio(video_path: str, output_wav_path: str, sample_rate: int = 16000) -> str:
    """Estrae l'audio da un video in formato WAV mono 16kHz ottimizzato per Whisper."""
    ffmpeg_exe = get_ffmpeg_binary()
    os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)
    
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", str(video_path),
        "-vn",
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
