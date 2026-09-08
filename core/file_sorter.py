import os
import shutil
import re
from typing import List, Dict
from dataclasses import dataclass
from core.pilot_detector import VideoPilotMatch

def sanitize_folder_name(name: str) -> str:
    """Rimuove caratteri non validi per i nomi di cartella su Windows/Linux."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean if clean else "Senza_Nome"

class FileSorter:
    def __init__(self, base_output_dir: str):
        self.base_output_dir = base_output_dir

    def sort_videos(self, matches: List[VideoPilotMatch], move: bool = False) -> Dict[str, List[str]]:
        """
        Smista i file video nelle cartelle dei rispettivi piloti.
        move: Se True sposta i file, se False li copia (default False per sicurezza dati).
        Restituisce un dizionario: { 'Nome_Pilota': [lista percorsi video nella nuova cartella] }
        """
        results: Dict[str, List[str]] = {}
        os.makedirs(self.base_output_dir, exist_ok=True)

        for match in matches:
            pilot_folder = sanitize_folder_name(match.detected_pilot)
            target_dir = os.path.join(self.base_output_dir, pilot_folder)
            os.makedirs(target_dir, exist_ok=True)

            target_file_path = os.path.join(target_dir, match.filename)

            if move:
                shutil.move(match.video_path, target_file_path)
            else:
                shutil.copy2(match.video_path, target_file_path)

            if pilot_folder not in results:
                results[pilot_folder] = []
            results[pilot_folder].append(target_file_path)

        return results
