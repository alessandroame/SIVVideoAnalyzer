# VideoAnalyzer - TODO & Roadmap

## 🚀 Prossimi Sviluppi & Feature Pianificate

*Nessuna lavorazione pendente. Tutti gli obiettivi operativi della roadmap sono stati completati.*

---

## ✅ Funzionalità Completate & Consolidate

- [x] **Dual-Tracking Sincronizzato nel Player (Riquadro Corpo Pilota & Riquadro Vela)**:
  - **Backend Computer Vision & Tracking (`core/tracking/`)**:
    - [`core/tracking/wing_tracker.py`](file:///d:/Github/VideoAnalyzer/core/tracking/wing_tracker.py): segmentazione cromatica HSV vettoriale per isolamento vela da cielo e lago, calcolo bounding box con percentili (1% e 99%) e padding dinamico per non tagliare le estremità dell'ala.
    - [`core/tracking/pilot_tracker.py`](file:///d:/Github/VideoAnalyzer/core/tracking/pilot_tracker.py): tracciamento del corpo del pilota basato sull'ancoraggio fisico al pendolo della calotta e sull'analisi del gradiente locale ad alto contrasto dell'imbrago.
    - [`core/tracking/smoother.py`](file:///d:/Github/VideoAnalyzer/core/tracking/smoother.py): stabilizzatore temporale con filtro esponenziale (EMA dinamico con velocity boost) per eliminare il tremolio della camera e interpolatore continuo per qualsiasi framerate di riproduzione.
    - [`core/tracking/pipeline.py`](file:///d:/Github/VideoAnalyzer/core/tracking/pipeline.py): pipeline di scansione video ad alte prestazioni con PyAV (`av`).
    - [`core/sidecar_manager.py`](file:///d:/Github/VideoAnalyzer/core/sidecar_manager.py): persistenza automatica del blocco `tracking` nei file sidecar `.json` per riapertura istantanea su qualsiasi PC (zero ricalcoli).
  - **Frontend & Rendering PyQt6 (`ui/`)**:
    - [`ui/components/tracking_pip_widget.py`](file:///d:/Github/VideoAnalyzer/ui/components/tracking_pip_widget.py): widget Picture-in-Picture con bordi cromatici tematici (Ciano per Pilota, Arancio per Vela), zoom dinamico regolabile con rotellina del mouse (1.0x - 3.0x), trascinamento libero con il mouse e doppio clic per focus.
    - [`ui/components/tracking_overlay.py`](file:///d:/Github/VideoAnalyzer/ui/components/tracking_overlay.py): overlay trasparente sul video master che intercetta i fotogrammi da `QVideoSink.videoFrameChanged` ed estrae i crop in tempo reale (~10 ms), disegnando i riquadri di delimitazione coordinati.
    - [`ui/tracking_worker.py`](file:///d:/Github/VideoAnalyzer/ui/tracking_worker.py): worker asincrono (`QThread`) con feedback in tempo reale dello stato di avanzamento.
    - [`ui/components/siv_video_widget.py`](file:///d:/Github/VideoAnalyzer/ui/components/siv_video_widget.py): isolamento del componente video per rispettare i limiti dimensionali dei file.
    - Pulsante dedicato `🎯 Tracking (T)` nella barra comandi del player e scorciatoia globale tasto `T` per attivare o nascondere i riquadri all'istante con una sola mano.
    - Suite di test dedicata in [`tests/test_tracking.py`](file:///d:/Github/VideoAnalyzer/tests/test_tracking.py) (6 test superati con successo).

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

