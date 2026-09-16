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
            import ctranslate2
            import os
            import numpy as np

            dev = self.device
            c_type = self.compute_type
            cpu_threads = os.cpu_count() or 4

            if dev == "auto":
                try:
                    if ctranslate2.get_cuda_device_count() > 0:
                        dev = "cuda"
                    else:
                        dev = "cpu"
                except Exception:
                    dev = "cpu"

            # Se è richiesto o rilevato CUDA, testiamo se le DLL cuBLAS/cuDNN sono presenti nel sistema
            if dev == "cuda":
                try:
                    cuda_c_type = "float16" if c_type == "default" else c_type
                    cand = WhisperModel(
                        self.model_size,
                        device="cuda",
                        compute_type=cuda_c_type,
                        cpu_threads=cpu_threads,
                        num_workers=2
                    )
                    # Verifica che cublas64_12.dll sia effettivamente presente e funzionante
                    dummy_audio = np.zeros(16000, dtype=np.float32)
                    cand.detect_language(dummy_audio)
                    self._model = cand
                    print(f"[Transcriber] Whisper inizializzato con successo su GPU CUDA ({cuda_c_type}).")
                except Exception as e:
                    print(f"[Transcriber] GPU rilevata ma runtime CUDA non disponibile ({e}). Fallback automatico su CPU ultra-rapida (int8)...")
                    dev = "cpu"

            if dev == "cpu":
                cpu_c_type = "int8" if c_type == "default" else c_type
                self._model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type=cpu_c_type,
                    cpu_threads=cpu_threads,
                    num_workers=2
                )
                print(f"[Transcriber] Whisper inizializzato con successo su CPU ({cpu_c_type}, {cpu_threads} thread).")

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

        try:
            segments, info = model.transcribe(
                audio_path,
                language=language,
                beam_size=beam_size,
                initial_prompt=siv_initial_prompt,
                vad_filter=False,
                condition_on_previous_text=False
            )
        except Exception as e:
            if "cublas" in str(e).lower() or "cuda" in str(e).lower():
                print(f"[Transcriber] Errore CUDA a runtime ({e}). Fallback forzato su CPU...")
                self.device = "cpu"
                self._model = None
                model = self.load_model()
                segments, info = model.transcribe(
                    audio_path,
                    language=language,
                    beam_size=beam_size,
                    initial_prompt=siv_initial_prompt,
                    vad_filter=False,
                    condition_on_previous_text=False
                )
            else:
                raise e

        result = []
        try:
            for s in segments:
                if is_cancelled_callback and is_cancelled_callback():
                    break
                seg = TranscriptionSegment(start=s.start, end=s.end, text=s.text.strip())
                result.append(seg)
                if progress_callback:
                    # Se il callback ritorna False o stop, interrompe tempestivamente (early exit)
                    cb_res = progress_callback(seg)
                    if cb_res is False:
                        break
        except Exception as e:
            if "cublas" in str(e).lower() or "cuda" in str(e).lower():
                print(f"[Transcriber] Errore CUDA durante l'iterazione ({e}). Fallback forzato su CPU...")
                self.device = "cpu"
                self._model = None
                return self.transcribe(
                    audio_path,
                    language=language,
                    beam_size=beam_size,
                    progress_callback=progress_callback,
                    is_cancelled_callback=is_cancelled_callback
                )
            else:
                raise e

        return result

