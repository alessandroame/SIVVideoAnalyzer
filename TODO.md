# VideoAnalyzer - TODO & Roadmap

## Feature & Miglioramenti in Corso / Pianificati

- [ ] **Wing Color Detector (Supporto Matching Pilota con Colore Vela)**
  - [ ] Implementare modulo `core/wing_color_detector.py` per estrazione veloce frame (15%, 30%, 50% durata).
  - [ ] Algoritmo leggero di filtraggio cielo/sfondo ed estrazione palette dominante in spazio HSV.
  - [ ] Sistema di "Auto-learning" firme cromatiche: associa il colore della vela ai piloti confermati via radio.
  - [ ] Integrazione in `core/pilot_detector.py` come booster/fallback per i video "Da Assegnare" o a bassa confidenza.
  - [ ] Mostrare i colori dominanti della vela come badge/pallino visivo nella tabella di revisione Step 2 (`ui/step2_review_view.py`).
- [ ] **Rilevamento Intelligente Video Già Analizzati (Step 1)**
  - [ ] Scansione preventiva rapida (cache locale `temp/` e manifest/output `output_siv/`).
  - [ ] Avviso chiaro nello Step 1 con stato dei video rilevati (già analizzati vs mancanti).
  - [ ] Se tutti i video sono già stati analizzati: avvisa l'utente e chiedi conferma (es. procedere alla revisione o rieseguire da zero), evitando salti improvvisi non richiesti.
  - [ ] Se solo alcuni video sono già analizzati: proponi esplicitamente *"Analizza solo i video mancanti"* (risparmiando tempo di trascrizione Whisper).

---

## Completati
- [x] Ordinamento temporale e smistamento video per data/ora fotocamera.
- [x] Trascrizione vocale offline con Whisper su QThread asincrono.
- [x] Riconoscimento radio del pilota e delle manovre SIV con fuzzy matching.
- [x] Player multimediale con capitoli automatici per manovra e timeline interattiva.
- [x] Raggruppamento multi-step guidato: Step 1 (Selezione/Configurazione) -> Step 2 (Revisione e Approvazione) -> Step 3 (Hub Montato).
