# SIV Video Analyzer

Software stand-alone desktop per l'analisi, catalogazione, montaggio e capitoli per video SIV parapendio.

## Avvio rapido
```bash
.\venv\Scripts\activate
python main.py
```

## Architettura a Wizard Guidato (3 Step)
1. **Step 1 - Configurazione & Riconoscimento Piloti**:
   - Selezione cartella video sorgente e cartella di destinazione (con memoria persistente).
   - Inserimento lista nomi piloti del corso per agevolare il matching radio Whisper.
   - Monitoraggio del progresso della trascrizione audio in tempo reale.
2. **Step 2 - Revisione & Assegnazione Video**:
   - Vista a schermo intero con tabella per verificare e riassegnare i piloti associati ai video.
   - Pulsanti di navigazione per tornare indietro o confermare il montaggio concatenato.
3. **Step 3 - Hub Finale, Player & Capitoli Manovre SIV**:
   - Menu a tendina per selezionare istantaneamente il pilota.
   - Caricamento automatico del video montato (`montati/<Pilota>_Corso_SIV_Montato.mp4`).
   - Ricomposizione istantanea senza ri-trascrizione della timeline e dei capitoli tramite cache.
   - Player video integrato con salto al minutaggio (doppio click) ed esportazione capitoli in formato YouTube / TXT.
