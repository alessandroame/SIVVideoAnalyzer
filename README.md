# SIV Video Analyzer

Software stand-alone desktop per l'analisi audio radio, catalogazione, debriefing didattico per volo e montaggio video per corsi SIV di parapendio.

## Avvio rapido
```bash
.\venv\Scripts\activate
python main.py
```

## Architettura Didattica per Volo (3 Step)
1. **Step 1 - Configurazione, Schede Piloti (Vele e Colori) & Riconoscimento Radio**:
   - Selezione cartella sorgente (inclusi formati Sony .MTS/.MXF da schede SD) e cartella di output portatile.
   - Anagrafica piloti (Nome, Modello Vela, Colori Vela) persistente in locale e su `corso_siv_manifest.json`.
   - Trascrizione Whisper con Speech-to-Text ultra-veloce (VAD attivo, vocabolario SIV) e stima tempo residuo (ETA).
2. **Step 2 - Revisione Video & Assegnazione per Volo**:
   - Tabella a schermo intero con associazione Pilota e **Numero di Volo** (`Volo 1`, `Volo 2`, ...).
   - Passaggio immediato al debriefing senza tempi morti di rendering video.
3. **Step 3 - Hub Debriefing Didattico, Player & Export Chiavetta**:
   - Navigazione a due livelli: **Pilota** + **Volo** per analizzare subito a lezione il volo appena concluso.
   - Player video sincronizzato con tabella manovre SIV e salto al minutaggio.
   - **Export Chiavetta Pilota**: generazione a fine giornata di video per singolo volo o video master montato con capitoli, titoli di transizione e sottotitoli/sovrimpressioni.

## Documentazione e Roadmap
I piani completi e la sequenza dei TODO consolidati sono disponibili in:
- [`docs/ROADMAP_CONSOLIDATA.md`](docs/ROADMAP_CONSOLIDATA.md)
- [`docs/PIANO_SIV_DIDATTICA_VOLI.md`](docs/PIANO_SIV_DIDATTICA_VOLI.md)
