# VideoAnalyzer - TODO & Roadmap

## 🚀 Prossimi Sviluppi & Feature Pianificate

*Nessuna lavorazione pendente. Tutti gli obiettivi operativi della roadmap sono stati completati.*

---

## ✅ Funzionalità Completate & Consolidate

- [x] **Feedback & Progressione Live Rilevamento Manovre & Selezione Engine**:
  - Tasto **🎯 Rileva Manovre...** dedicato nel player video di debriefing con finestra di selezione engine/modello Whisper (`small`, `medium`, `large-v3`).
  - Segnalazione dello stato e avanzamento percentuale del rilevamento manovre sia nel player video di debriefing che nella tabella voli.
  - Indicatore di avanzamento sottile (`QProgressBar` e stato testuale es. *"⏳ Ascolto radio istruttore (Whisper)..."* $\rightarrow$ *"✅ X manovre rilevate"*) nel pannello **CAPITOLI & MANOVRE** del player.
  - Badge reattivo con conteggio e stato nel pulsante Debriefing della tabella voli (`▶ Guarda (3)` o `⏳ 70%`), con tooltip descrittivo dello stato corrente.
  - Thread worker on-demand dedicato [`ManeuverCalculationWorker`](file:///c:/github/SIVVideoAnalyzer/ui/maneuver_worker.py) con supporto a forzatura ricalcolo e pipeline [`AnalysisWorker`](file:///c:/github/SIVVideoAnalyzer/ui/workers.py) sincronizzati via segnali PyQt6.
  - Classificazione manovre unificata: rimossa la distinzione destra/sinistra (es. *"Chiusura Asimmetrica"*) per evitare complessità inutile e massimizzare l'accuratezza del matching radio.

- [x] **Wing Color Detector (Matching Vela & Supporto Visivo)**:
  - Modulo [`core/wing_color_detector.py`](file:///c:/github/SIVVideoAnalyzer/core/wing_color_detector.py) con campionamento frame FFmpeg ultra-rapido (senza OpenCV/PIL).
  - Filtraggio dello sfondo (cielo/lago) e categorizzazione HSV dei colori saturi.
  - Widget [`GliderBadgeWidget`](file:///c:/github/SIVVideoAnalyzer/ui/components/glider_badge.py) con pallini cromatici visivi nella tabella voli.
  - Fallback intelligente di assegnazione pilota basato sul colore della vela se la radio è assente o disturbata dal vento.

- [x] **Rilevamento Intelligente Clip Già Analizzate (Startup & Cache)**:
  - Scansione preventiva rapida in [`core/session_scanner.py`](file:///c:/github/SIVVideoAnalyzer/core/session_scanner.py).
  - Feedback visuale dinamico nella Welcome Card con conteggio clip pronte e pendenti.
  - Avvio intelligente che instrada al worker solo le clip mancanti, risparmiando tempo di trascrizione Whisper.
  - Auto-importazione dei piloti e delle vele dai metadati sidecar esistenti con un clic.

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

