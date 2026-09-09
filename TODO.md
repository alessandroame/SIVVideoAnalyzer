# VideoAnalyzer - TODO & Roadmap

## 🚀 Prossimi Sviluppi & Feature Pianificate

### 1. Rilevamento Intelligente Clip Già Analizzate (Startup & Cache)
- [ ] **Scansione Preventiva Rapida**: All'inserimento della cartella video, controllare la presenza di file sidecar `.siv.json` o cache `temp/`.
- [ ] **Feedback Chiave per l'Istruttore**: Segnalare chiaramente lo stato (es. *"8 clip su 10 già pronte"*).
- [ ] **Opzione Salto / Analisi Selettiva**: Consentire di cliccare *"Analizza solo i mancanti"* o *"Apri direttamente registro"* risparmiando tempo di trascrizione Whisper.

### 2. Wing Color Detector (Matching Vela & Supporto Visivo)
- [ ] **Modulo `core/wing_color_detector.py`**: Estrazione rapida frame chiave (15%, 30%, 50% durata).
- [ ] **Filtraggio Cielo/Sfondo**: Estrazione palette cromatica dominante in spazio colore HSV.
- [ ] **Badge Cromatico nel Registro**: Mostrare un pallino/badge con i colori principali della vela nella tabella voli.
- [ ] **Fallback Assegnazione**: Supporto per assegnare le clip "Da Assegnare" quando la voce radio è coperta dal fruscio del vento.

### 3. Modalità "Apri Sessione Esistente (Replay)"
- [ ] **Pulsante dedicato nella Welcome Card**: Consente di aprire direttamente una cartella o chiavetta USB con video e metadati già pronti, passando subito al Registro Voli senza riconfigurare i piloti.

---

## ✅ Funzionalità Completate & Consolidate

- [x] **Architettura Dual-Mode Reattiva (Material Design 3)**:
  - Welcome & Setup $\leftrightarrow$ **Registro Voli Live** (Tabella Streaming) $\leftrightarrow$ **Debriefing Room** (Player Video & Capitoli).
  - Eliminato il vecchio wizard rigido in favore di un flusso live senza tempi morti.
- [x] **Trascrizione Vocale & Assegnazione Pilota**:
  - Trascrizione Whisper offline su thread asincrono non bloccante.
  - Riconoscimento chiamate radio con fuzzy matching su anagrafica piloti.
- [x] **Rilevamento Intelligente Numero di Volo**:
  - Identificazione automatica del volo (`Volo 1`, `Volo 2`...) dai comandi radio dell'istruttore e dalla data/ora fotocamera (`ffprobe`).
  - Possibilità di modifica rapida del numero di volo con `QSpinBox` direttamente nella tabella.
- [x] **Debriefing Zero-Render con Priorità Live**:
  - L'istruttore può aprire qualsiasi clip all'istante: il worker analizza prioritariamente le manovre della clip selezionata.
  - Player video integrato con timeline dei capitoli interattiva, note didattiche e comandi dell'istruttore.
- [x] **Portabilità & File Sidecar `.siv.json`**:
  - I dati di ciascun volo (pilota, numero di volo, capitoli e comandi) vengono salvati in file `.siv.json` portatili a fianco del video.
- [x] **Esportazione Video Pilota & Chiavette USB**:
  - Modulo `VideoExporter` integrato in `core/flight_grouper.py`.
  - Esportazione singolo volo o batch ("Esporta Tutti i Voli") nella cartella per i piloti, con unione automatica clip e generazione file capitoli YouTube.
- [x] **Compatibilità e Resilienza Icone UI**:
  - Correzione frecce up/down degli spinbox e layout responsive dark slate & cyan.

