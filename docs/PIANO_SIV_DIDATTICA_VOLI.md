# Piano Operativo SIV: Struttura Output Portatile al 100% (Chiavetta USB & Multi-PC)

Questo piano integra i requisiti di **portabilità assoluta**, **organizzazione didattica per volo** e **gestione avanzata dei piloti** (inclusi modello e colori della vela).

La cartella di Output (es. su chiavetta USB o disco esterno) deve essere un **pacchetto autonomo e auto-consistente (Plug & Play)**: aprendola su qualunque altro computer o riaprendo l'applicazione, tutto il corso SIV deve essere immediatamente accessibile senza ricalcolare trascrizioni, senza perdere i dati dei piloti e senza dipendere dalla cartella `temp` locale del PC originario.

---

## 1. Struttura del Pacchetto Portatile (`output_siv/`)

Ogni corso esportato su cartella o chiavetta conterrà il file manifesto principale `corso_siv_manifest.json`:

```text
chiavetta_usb / output_siv/
│
├── corso_siv_manifest.json              # Anagrafica del corso: piloti, vele, colori, data
│
├── Marco_Rossi/
│   ├── pilota_info.json                 # Scheda del pilota: vela, colore, imbrago, note
│   ├── Volo_01/
│   │   ├── clip_001.MP4                 # Video del volo
│   │   ├── trascrizione.json            # Trascrizione temporizzata completa del volo
│   │   ├── capitoli.json                # Manovre riconosciute ed editate
│   │   └── capitoli_youtube.txt         # Esportazione testo / YouTube
│   └── Volo_02/
│       ├── clip_002.MP4
│       ├── trascrizione.json
│       └── capitoli.json
│
├── Alessandro_Bianchi/
│   ├── pilota_info.json
│   ├── Volo_01/
│   │   ├── 00311.MP4
│   │   ├── trascrizione.json
│   │   └── capitoli.json
│   └── Volo_02/
│       ├── 00319.MP4
│       ├── 00320.MP4
│       ├── trascrizione.json
│       └── capitoli.json
│
└── export_montati/                      # (Opzionale: generato solo su richiesta a fine corso)
    ├── Marco_Rossi_Corso_SIV.mp4
    └── Alessandro_Bianchi_Corso_SIV.mp4
```

---

## 2. Dettaglio dei Metadati: `corso_siv_manifest.json`

Permette a qualsiasi computer di caricare all'istante l'intero corso con piloti, caratteristiche delle vele e voli:

```json
{
  "nome_corso": "SIV Lago di Garda - Settembre 2026",
  "data_inizio": "2026-09-08",
  "data_fine": "2026-09-10",
  "istruttore": "Istruttore SIV",
  "piloti": [
    {
      "id": "alessandro_bianchi",
      "nome": "Alessandro Bianchi",
      "vela_marca_modello": "Ozone Rush 6",
      "colori_vela": "Rosso / Bianco / Nero",
      "imbrago": "Woody Valley GTO Light 2",
      "livello": "Intermedio / Progressione",
      "note": "Focus su controllo beccheggio e uscita pulita da spirale",
      "cartella": "Alessandro_Bianchi"
    },
    {
      "id": "marco_rossi",
      "nome": "Marco Rossi",
      "vela_marca_modello": "Advance Iota DLS",
      "colori_vela": "Lime / Blu",
      "imbrago": "Supair Strike 2",
      "livello": "Sicurezza base",
      "note": "Prima volta su full stall",
      "cartella": "Marco_Rossi"
    }
  ]
}
```

---

## 3. Gestione Schede Pilota nella UI (Step 1)

Invece di un semplice campo testo `txt_pilots`, aggiungeremo una gestione schede pilota amichevole:
- **Nome e Cognome**: es. `Alessandro Bianchi`
- **Modello Vela**: es. `Ozone Rush 6`
- **Colori Vela**: es. `Rosso/Nero`
- Tasto `+ Aggiungi Pilota` e `Rimuovi`.
- Tutti questi dati vengono salvati sia in locale con `QSettings` sia direttamente nel `corso_siv_manifest.json` nella cartella di destinazione.

---

## 4. Debriefing Dinamico per Volo (Tra un decollo e l'altro)

- I video vengono smistati in `output_siv/<Pilota>/Volo_01/`, `Volo_02/`...
- Le trascrizioni `.json` vengono salvate **direttamente nella cartella del volo** (e non più solo nella cache `temp` volatile del PC).
- Nel player dello Step 3:
  - Selettore Pilota: `[ Alessandro Bianchi (Ozone Rush 6 - Rosso/Bianco) ▼ ]`
  - Selettore Volo: `[ ✈ Volo 1 (2 manovre) | ✈ Volo 2 (4 manovre) ]`
  - **Zero attese di montaggio video**: il player carica istantaneamente i file originali del volo e salta sulle manovre con precisione assoluta.

---

## 5. Portabilità su Memory Stick / Altro PC ("Plug & Play")

Quando l'istruttore o il pilota inserisce la chiavetta su un altro PC:
1. Apre il programma e clicca **"📂 Apri Sessione SIV Esistente"**.
2. Seleziona la cartella sulla chiavetta.
3. Il software rileva `corso_siv_manifest.json` e:
   - Carica all'istante l'elenco dei piloti con i dati della vela.
   - Legge tutte le trascrizioni e i capitoli già calcolati.
   - Si apre direttamente nello **Step 3 (Player & Debriefing)**.
   - **Nessun calcolo di Whisper, nessuna CPU/GPU impegnata, 0 secondi di attesa.**

---

## 6. Export Finale per Chiavette USB Piloti

A fine giornata / corso, l'istruttore usa la funzione di esportazione per produrre i file finali:
- **Opzione 1 (Per Volo)**: genera un video unificato per ciascun volo del pilota (`Alessandro_Volo_1.mp4`, `Alessandro_Volo_2.mp4`) con capitoli YouTube inclusi.
- **Opzione 2 (Video Completo Corso)**: unisce tutti i voli in sequenza, inserendo un cartello separatore grafico tra i voli (*"Volo 1 - Asimmetriche"*, *"Volo 2 - Stalli"*).
- **Opzione Sottotitoli / Sovrimpressione**:
  - File `.srt` sincronizzato per ogni manovra e comando radio.
  - Oppure sovraimpressione video (overlay burn-in): `[ VOLO 1 ] - CHIUSURA ASIMMETRICA 50%`.

---

## 7. Tabella di Marcia dello Sviluppo

- [ ] **Step A**: Creazione modulo `core/manifest_manager.py` per salvare e caricare `corso_siv_manifest.json` e `pilota_info.json`.
- [ ] **Step B**: UI Step 1 con gestione piloti arricchita (Nome, Vela, Colori) e salvataggio automatico nel manifest.
- [ ] **Step C**: Raggruppamento automatico delle clip per sessione di volo (`Volo_01`, `Volo_02`) basato sul gap temporale tra i video.
- [ ] **Step D**: Salvataggio di `trascrizione.json` e `capitoli.json` all'interno di ogni cartella di volo per totale portabilità.
- [ ] **Step E**: Player Step 3 con navigazione a due livelli `Pilota ➔ Volo ➔ Manovra` senza rendering preventivo.
- [ ] **Step F**: Pulsante e logica "Apri Sessione Esistente (Plug & Play)" per chiavette USB e dischi esterni.
- [ ] **Step G**: Modulo di esportazione finale (montato per volo / montato completo con sovrimpressioni e sottotitoli).
