# Piano di Sviluppo: Modalità Pure Replay & Struttura Output Autonoma

Questo documento definisce l'architettura e i requisiti per rendere la cartella di **Output** completamente autonoma e portatile, consentendo di aprire qualsiasi sessione o corso SIV già montato in modalità **Pure Replay** (Player + Capitoli) all'istante, senza ricalcolare nulla e senza dipendere dalla cache temporanea.

---

## 1. Struttura dei File di Output per Pilota

Al momento della concatenazione dei video (e ad ogni modifica manuale dei capitoli nello Step 3), dentro la cartella `output_siv/<NomePilota>/montati/` vengono generati e mantenuti:

```text
output_siv/
└── <NomePilota>/
    ├── 00311.MP4                   # Clip sorgente originali del pilota
    ├── 00319.MP4
    └── montati/
        ├── <NomePilota>_Corso_SIV_Montato.mp4   # Video montato unificato
        ├── capitoli.json                       # Metadati completi dei capitoli SIV
        ├── capitoli.txt                        # Formato testo / YouTube
        └── trascrizione_timeline.json          # Trascrizione temporizzata completa
```

### Specifiche di `capitoli.json`
```json
[
  {
    "start_time": 45.2,
    "end_time": 52.0,
    "formatted_start": "00:45",
    "maneuver_id": "chiusura_asimmetrica",
    "maneuver_name": "Chiusura Asimmetrica 50%",
    "category": "Asimmetriche",
    "transcription_text": "allora vai a chiusura a sinistra convirata a destra",
    "confidence": 0.95
  }
]
```

---

## 2. Modalità "Pure Replay"

### A. Accesso Rapido nello Step 1
- Pulsante dedicato in primo piano nello Step 1:
  **"📂 Apri Sessione Esistente (Replay / Capitoli)"**.
- Consente all'utente di selezionare una cartella `output_siv` (o la cartella di un corso specifico).

### B. Caricamento Istantaneo (Zero Elaborazione)
- Scansione della cartella:
  - Rileva tutti i piloti che dispongono di un file `montati/*_Montato.mp4`.
  - Legge `capitoli.json` associato (con fallback su `capitoli.txt`).
- Transizione immediata allo **Step 3 (Player & Manovre SIV)**:
  - Menu a tendina popolato con tutti i piloti rilevati.
  - Video caricato e pronto per la riproduzione.
  - Tabella capitoli popolata e funzionante con salto al minutaggio (doppio click).

### C. Salvataggio Modifiche Capitoli
- Nello Step 3 viene aggiunto il pulsante **"💾 Salva Modifiche Capitoli"**:
  - Permette di modificare i nomi delle manovre, aggiungere nuovi punti di interesse o rimuoverne, riscrivendo direttamente `capitoli.json` e `capitoli.txt` nella cartella `montati/`.

---

## 3. Roadmap di Implementazione

1. **`core/maneuver_detector.py`**:
   - Aggiunta funzioni di esportazione/importazione JSON per `SIVChapter` (`save_chapters_to_json` e `load_chapters_from_json`).
2. **`ui/main_window.py`**:
   - Salvataggio automatico dei file `capitoli.json` e `capitoli.txt` in `montati/` al completamento del montaggio.
   - Pulsante *"📂 Apri Sessione Esistente (Replay)"* nello Step 1 e logica di apertura istantanea verso lo Step 3.
3. **`ui/step3_chapters_view.py`**:
   - Pulsante *"💾 Salva Modifiche"* per aggiornare su disco le modifiche apportate alla tabella capitoli.
