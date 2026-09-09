from dataclasses import dataclass
from typing import List, Optional

@dataclass
class TranscriptionSegment:
    start: float
    end: float
    text: str

class SIVTranscriber:
    def __init__(self, model_size: str = "small", device: str = "auto", compute_type: str = "default"):
        """
        Inizializza il motore faster-whisper.
        model_size: 'small', 'medium'
        device: 'cuda', 'cpu', 'auto'
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._loaded_model_size = None

    def set_model_size(self, model_size: str):
        if model_size != self.model_size:
            self.model_size = model_size
            self._model = None  # Forza il ricaricamento del nuovo modello

    def load_model(self):
        if self._model is None or self._loaded_model_size != self.model_size:
            from faster_whisper import WhisperModel
            dev = self.device
            c_type = self.compute_type
            if dev == "auto":
                try:
                    import torch
                    dev = "cuda" if torch.cuda.is_available() else "cpu"
                except Exception:
                    dev = "cpu"
            
            if dev == "cpu" and c_type == "default":
                c_type = "int8"
            elif dev == "cuda" and c_type == "default":
                c_type = "float16"

            import os
            cpu_threads = os.cpu_count() or 4
            self._model = WhisperModel(
                self.model_size,
                device=dev,
                compute_type=c_type,
                cpu_threads=cpu_threads,
                num_workers=2
            )
            self._loaded_model_size = self.model_size
        return self._model

    def transcribe(self, audio_path: str, language: str = "it", beam_size: int = 1, progress_callback=None, is_cancelled_callback=None) -> List[TranscriptionSegment]:
        model = self.load_model()

        # Prompt contestuale SIV per guidare la rete neurale sul vocabolario specifico del parapendio
        siv_initial_prompt = (
            "Corso SIV di parapendio. Comunicazioni radio dell'istruttore: "
            "chiusura asimmetrica 30% 50% 75%, chiudi destra, chiudi sinistra, frontale, "
            "orecchie, grandi orecchie, speed bar, acceleratore, spirale picchiata, vite, "
            "uscita progressiva, wingover, inversione di rollio, delfinaggio, beccheggio, "
            "b-stall, stallo di b, full stall, stallo pieno, backfly, retrocessione, spin, "
            "negativa, autorotazione, radio check, sei in box, pronto per l'esercizio, vai, via, lascia, "
            "fanne un'altra, facciamone un'altra, riproviamo, riprova, ancora una, rifalla, un'altra uguale, "
            "stessa cosa, altra volta, 3 2 1 via tira deciso."
        )

        # Disattivato vad_filter: il VAD (Silero) nei corsi SIV interpreta il fruscio del vento
        # e le lunghe pause tra le manovre come silenzio totale, tagliando l'audio dopo pochi secondi.
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=beam_size,
            initial_prompt=siv_initial_prompt,
            vad_filter=False,
            condition_on_previous_text=False
        )
        
        result = []
        for s in segments:
            if is_cancelled_callback and is_cancelled_callback():
                break
            seg = TranscriptionSegment(start=s.start, end=s.end, text=s.text.strip())
            result.append(seg)
            if progress_callback:
                progress_callback(seg)
                
        return result

