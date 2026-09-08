# VideoAnalyzer - TODO & Roadmap

## Feature & Miglioramenti in Corso / Pianificati

- [ ] **Wing Color Detector (Supporto Matching Pilota con Colore Vela)**
  - [ ] Implementare modulo `core/wing_color_detector.py` per estrazione veloce frame (15%, 30%, 50% durata).
  - [ ] Algoritmo leggero di filtraggio cielo/sfondo ed estrazione palette dominante in spazio HSV.
  - [ ] Sistema di "Auto-learning" firme cromatiche: associa il colore della vela ai piloti confermati via radio.
  - [ ] Integrazione in `core/pilot_detector.py` come booster/fallback per i video "Da Assegnare" o a bassa confidenza.
  - [ ] Mostrare i colori dominanti della vela come badge/pallino visivo nella tabella di revisione Step 2 (`ui/step2_review_view.py`).
  - [ ] Test unitari dedicati in `tests/test_wing_color_detector.py`.

---

## Completati
- [x] Ordinamento temporale e smistamento video per data/ora fotocamera.
- [x] Trascrizione vocale offline con Whisper su QThread asincrono.
- [x] Riconoscimento radio del pilota e delle manovre SIV con fuzzy matching.
- [x] Player multimediale con capitoli automatici per manovra e timeline interattiva.
- [x] Raggruppamento multi-step guidato: Step 1 (Selezione/Configurazione) -> Step 2 (Revisione e Approvazione) -> Step 3 (Hub Montato).
