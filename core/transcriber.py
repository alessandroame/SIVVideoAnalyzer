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
        model_size: 'base', 'small', 'medium'
        device: 'cuda', 'cpu', 'auto'
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            # Se auto, prova cuda se c'è torch.cuda o ripiega su cpu con int8
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

            self._model = WhisperModel(self.model_size, device=dev, compute_type=c_type)
        return self._model

    def transcribe(self, audio_path: str, language: str = "it", progress_callback=None) -> List[TranscriptionSegment]:
        model = self.load_model()
        # Disabilitiamo vad_filter aggressivo che causava l'arresto anticipato in presenza di fruscio del vento
        # e aumentiamo la tolleranza al rumore di fondo tipico dei voli in parapendio.
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=False,  # Garantisce che l'intero audio venga processato da 00:00 fino all'ultimo secondo
            condition_on_previous_text=False,  # Evita loop di allucinazioni o blocchi dopo tratti di silenzio
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0
        )
        
        result = []
        for s in segments:
            seg = TranscriptionSegment(start=s.start, end=s.end, text=s.text.strip())
            result.append(seg)
            if progress_callback:
                progress_callback(seg)
                
        return result
