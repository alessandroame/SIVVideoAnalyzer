import os
import subprocess
from typing import List
from pathlib import Path
from core.audio_extractor import get_ffmpeg_binary

class VideoConcatenator:
    def __init__(self, temp_dir: str = "temp"):
        self.temp_dir = temp_dir
        self.ffmpeg_exe = get_ffmpeg_binary()

    def concatenate_videos(self, video_paths: List[str], output_video_path: str, progress_callback=None) -> str:
        """
        Unisce i video in ordine cronologico.
        Tenta prima il demuxer concat (lossless, velocissimo in pochi secondi senza ricodifica).
        Se fallisce (es. codec o risoluzioni diverse), esegue ricodifica compatibile.
        """
        if not video_paths:
            raise ValueError("Nessun video fornito per la concatenazione.")

        if len(video_paths) == 1:
            # Un solo video: se diverso dal target, copialo o collegalo
            import shutil
            os.makedirs(os.path.dirname(output_video_path), exist_ok=True)
            shutil.copy2(video_paths[0], output_video_path)
            return output_video_path

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(os.path.dirname(output_video_path), exist_ok=True)

        # Crea file elenco per concat demuxer
        concat_list_file = os.path.join(self.temp_dir, "concat_list.txt")
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for vp in video_paths:
                # Per ffmpeg concat demuxer i path devono essere formattati correttamente
                abs_p = os.path.abspath(vp).replace("\\", "/")
                f.write(f"file '{abs_p}'\n")

        # Tentativo 1: Concat Demuxer Lossless (-c copy)
        cmd_copy = [
            self.ffmpeg_exe,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_file,
            "-c", "copy",
            str(output_video_path)
        ]

        result = subprocess.run(cmd_copy, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            # Fallback: ricodifica se i formati dei file differiscono
            filter_inputs = "".join([f"[{i}:v:0][{i}:a:0]" for i in range(len(video_paths))])
            filter_complex = f"{filter_inputs}concat=n={len(video_paths)}:v=1:a=1[outv][outa]"

            cmd_reencode = [self.ffmpeg_exe, "-y"]
            for vp in video_paths:
                cmd_reencode.extend(["-i", str(vp)])

            cmd_reencode.extend([
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_video_path)
            ])

            res_reencode = subprocess.run(cmd_reencode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res_reencode.returncode != 0:
                raise RuntimeError(f"Errore durante la concatenazione dei video: {res_reencode.stderr}")

        # Rimuovi file lista temporaneo
        if os.path.exists(concat_list_file):
            try:
                os.remove(concat_list_file)
            except Exception:
                pass

        return output_video_path
