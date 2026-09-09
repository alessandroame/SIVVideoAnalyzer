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
- Fase 1: Chiamata radio e verifica box ('Marco mi ricevi?', 'Radio check', 'Sei in box, pronto per l\'esercizio?', 'Alessandro, mantieni la prua').
- Fase 2: Briefing in aria ('Adesso facciamo le minime velocità', 'Chiusura asimmetrica a sinistra con mantenimento rotta', 'Portati ai limiti del lago per la frontale', 'Iniziamo a metà acceleratore').
- Fase 3: Comando esecutivo ('Pronto... 3, 2, 1, tira deciso!', 'Vai chiudi!', 'Tira le bretelle anteriori con un bel tiro deciso!', 'Sfonda a destra!').
- Fase 4: Pilotaggio attivo e correzione ('Contrasta col peso e col corpo', 'Tieni la prua verso l\'atterraggio', 'Non frenare la semiala aperta', 'Stai tirando troppo', 'Lascia scorrere').
- Fase 5: Uscita ('Rilascia progressivo', 'Mani alte', 'Lascia volare', 'Frena il beccheggio', 'Bravissimo, rimani a braccia alte').
- Fase 6: Smaltimento quota & Circuito ('Base sinistra/destra', 'Entra in sottovento', '180 a destra verso l\'atterraggio').

### B. Manovre SIV Standard & Didattica
- Asimmetriche: 30%, 50%, 75% non accelerate, con acceleratore (1/2 o full bar) e mantenimento di rotta/pilotaggio attivo della semiala aperta.
- Frontali: simmetrica e accelerata (trazione bretelle A anteriori con pollici verso il basso/alto e rilascio immediato).
- Minime Velocità (Slow Flight): rallentamento progressivo per riconoscere il punto di stallo, l'indurimento dei freni e la tendenza al paracadutale prima del rilascio.
- Grandi Orecchie e B-Stall: discese rapide controllate.
- Dinamica e Rollio: Pitching / Delfinaggio e Wingover (inversioni di rollio ritmate 'sinistra, lascia, destra, lascia', trasferimento di carico sull'imbrago).
- Spirale Picchiata (Spiral Dive) e uscita progressiva dissipata su 1-2 giri per evitare impennate o stalli d'uscita.
- Stalli & Autorotazioni: Full Stall, Backfly (volo retrogrado controllato), Spin/Negativa (stallo d'ala asimmetrico per rilascio o trazione asimmetrica) e autorotazione controllata.

### C. Analisi Acustica & Speech-to-Text nel Volo in Parapendio
- Rumore del vento e VAD: il vento relativo sul microfono dell'action cam o della radio può confondere i filtri VAD aggressivi. Usare `vad_filter=False` o VAD conservativo per non perdere i comandi brevi ('lascia', 'frena', 'destra').
- Gergo radio distorto: Whisper può trascrivere 'asimmetrica' come 'a simmetrica', 'semistra' per 'sinistra', 'pide in velocità' per 'minime velocità', 'prete le a' per 'bretelle A'. Le keyword in `siv_maneuvers.json` e il fuzzy matching devono considerare queste mutazioni fonetiche tipiche.

## 2. Best Practice Architettura & Packaging (.exe Stand-alone)

### A. PyInstaller Stand-alone Executable
- Utilizzare una cartella o installer Inno Setup / .spec per raggruppare i file.
- Supportare sys._MEIPASS tramite get_resource_path() per trovare file json, asset e modelli anche quando l\'app e eseguita come file .exe.
- Includere ffmpeg incorporato e cache modello Whisper per garantire funzionamento 100% offline.

### B. Threading & Reattività UI
- Mantenere sempre la GUI PyQt6 fluida usando QThread e segnali (pyqtSignal) per qualsiasi operazione pesante (Whisper, FFmpeg, sorting).

## 3. Contesto d'Uso: Ergonomia Cognitiva & Gestione dello Stress (Mission-Critical)

### A. Profilo Utente & Condizioni Operative
- L'utente tipo è un istruttore SIV reduce da ore sul gommone/spiaggia, sottoposto a intemperie, fatica fisica e forte tensione emotiva dovuta alla gestione in tempo reale della sicurezza e di emergenze in volo (stalli asimmetrici, cravatte, autorotazioni, ammaraggi con riserva).
- Al momento del debriefing l'istruttore è in debito di energie e con "tunnel vision" cognitiva: deve spiegare gli errori a 10-15 allievi in ansia prima di cena.
- **Assioma di Design:** L'interfaccia deve essere trattata come uno strumento di gestione dell'emergenza: zero frizione, zero parametri complessi, zero ambiguità, salvataggio continuo e automatico.

### B. I Principi UX/UI Inviolabili ("Stress-Free SIV Workflow")
1. **Flusso Lineare a 3 Sole Fasi Chiare:**
   - **Fase 1 (Accoglienza / Rampa di Lancio):** Solo selezione cartella video (con memoria automatica dell'ultima usata) e roster piloti (aggiunta rapida). Un solo grande tasto primario di avvio (`Invio`).
   - **Fase 2 (Tavolo di Lavoro / Registro Live):** Tabella essenziale con Giorno, Volo N°, Pilota/Vela, Stato. I dati si auto-popolano in background. Modifiche dirette nelle celle senza finestre modali o pulsanti "Salva".
   - **Fase 3 (Aula Debriefing / Player):** Schermo grande, video a pieno schermo con tasto `F` o doppio clic (`ESC` per tornare), comandi a 1 mano (`Spazio` play/pause, frecce $\pm 5$s), capitoli manovre a destra cliccabili per saltare istantaneamente all'inizio dell'esercizio.
2. **Priorità di Esecuzione Preemptive (Background Tasks):**
   - **P1 (Priorità Assoluta):** Il video correntemente aperto nel player scavalca qualsiasi altra elaborazione in coda per mostrare subito le manovre all'allievo.
   - **P2 (Media):** Riconoscimento nomi/voli nei video non ancora identificati.
   - **P3 (Bassa):** Riconoscimento a tappeto di tutte le manovre della sessione.
3. **Architettura Sidecar Non Distruttiva:**
   - I file video sorgente su scheda SD non vengono mai modificati né aperti in scrittura.
   - Tutte le annotazioni e i riconoscimenti risiedono in sidecar compatti `<video>.json`, garantendo portabilità istantanea su qualsiasi computer o chiavetta USB.
4. **Feedback Visivo Immediato a Semaforo:**
   - 🟢 Verde: Riconosciuto con certezza.
   - 🟡 Giallo: Suggerimento da confermare con 1 clic (tasto Invio).
   - ⏳ In elaborazione: Nessun blocco dell'interfaccia; il video rimane comunque riproducibile immediatamente.

## 4. Modularità del Codice & Separation of Concerns (SoC)

Per garantire la massima manutenibilità, leggibilità e velocità di sviluppo dell'agente:
- **Limite Dimensionale File**: Nessun file di interfaccia utente (`ui/`) deve superare le **350-400 righe**. Se un file si avvicina a questa soglia, va scomposto.
- **Separazione dei Ruoli**:
  1. `ui/workers.py`: Dedicato esclusivamente ai thread di background (`QThread`, `pyqtSignal`), elaborazioni asincrone (Whisper, export, worker queue).
  2. `ui/components/`: Directory dedicata ai widget UI specializzati (es. `flight_table.py`, `debriefing_player.py`, `welcome_card.py`). Ogni widget gestisce solo il proprio layout e i propri eventi visivi.
  3. `ui/dialogs/`: Finestre modali o dialoghi dedicati (es. `maneuvers_dialog.py`, `add_chapter_dialog.py`).
  4. `ui/main_window.py`: Orchestratore ad alto livello ("direttore d'orchestra"). Si limita a istanziare i componenti, comporre il layout generale (`QStackedWidget` / `QSplitter`) e connettere i segnali PyQt tra componenti e worker. Non contiene logica grafica pesante né logica di elaborazione.


