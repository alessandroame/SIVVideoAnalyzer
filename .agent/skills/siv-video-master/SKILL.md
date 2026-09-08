---
name: siv-video-master
description: Guida esperta per lo sviluppo e l\'ottimizzazione del software SIV Video Analyzer e profonda competenza didattica e tecnica sulle manovre e comunicazioni radio dei corsi SIV in parapendio.
---

# SIV Video Master & Software Architect Skill

Questa skill fornisce all\'agente la duplice competenza:
1. Istruttore SIV Senior & Pilota Acro/Sicurezza Parapendio: conoscenza approfondita della didattica dei corsi SIV, gergo radio, dinamiche di volo, sequenze di manovre e tempistiche di esecuzione.
2. Lead Desktop Software Engineer: padronanza dell\'architettura a basso impatto, packaging stand-alone (PyInstaller .exe), threading PyQt6, elaborazione video/audio con FFmpeg e speech-to-text offline con Whisper.

## 1. Conoscenza del Dominio SIV (Parapendio)

### A. Comunicazioni Radio Istruttore
- Fase 1: Chiamata radio e verifica box ('Marco mi ricevi?', 'Radio check', 'Sei in box, pronto per l\'esercizio?').
- Fase 2: Briefing in aria ('Adesso faremo un\'asimmetrica destra 50%').
- Fase 3: Comando esecutivo ('Pronto... 3, 2, 1, tira deciso!', 'Vai chiudi!').
- Fase 4: Pilotaggio attivo e correzione ('Contrasta col peso', 'Guarda la vela', 'Tieni la prua').
- Fase 5: Uscita ('Rilascia progressivo', 'Mani alte', 'Lascia volare', 'Frena il beccheggio').

### B. Manovre SIV Standard
- Asimmetriche: 30%, 50%, 75% non accelerate e con acceleratore.
- Frontali: simmetrica e accelerata (trazione bretelle A).
- Grandi Orecchie e B-Stall.
- Pitching / Delfinaggio e Wingover (inversioni di rollio).
- Spirale Picchiata (Spiral Dive) e uscita progressiva dissipata.
- Stalli: Full Stall, Backfly (volo retrogrado) e Spin/Negativa.

## 2. Best Practice Architettura & Packaging (.exe Stand-alone)

### A. PyInstaller Stand-alone Executable
- Utilizzare una cartella o installer Inno Setup / .spec per raggruppare i file.
- Supportare sys._MEIPASS tramite get_resource_path() per trovare file json, asset e modelli anche quando l\'app e eseguita come file .exe.
- Includere ffmpeg incorporato e cache modello Whisper per garantire funzionamento 100% offline.

### B. Threading & Reattività UI
- Mantenere sempre la GUI PyQt6 fluida usando QThread e segnali (pyqtSignal) per qualsiasi operazione pesante (Whisper, FFmpeg, sorting).
