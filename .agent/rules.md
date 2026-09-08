# Regole di Sviluppo & Competenza di Dominio SIV

1. **Competenza SIV e Terminologia di Volo**:
   - Mantenere sempre una comprensione tecnica rigorosa del vocabolario dei corsi SIV in parapendio (asimmetriche, frontali, speed bar, orecchie, B-stall, full stall, backfly, wingover, spirale, stallo d\'ala/negativa).
   - Tenere conto del fatto che l\'istruttore prima anticipa la manovra, poi dà il comando di esecuzione ('3, 2, 1, via', 'tira'), e infine corregge/fa uscire. Il capitolo deve agganciare con precisione l\'istante in cui la manovra inizia.

2. **Affidabilità Offline & Stand-Alone**:
   - Il software deve funzionare in modo completamente autonomo, offline sul PC dell\'istruttore o della scuola (anche al lago o in atterraggio senza Wi-Fi).
   - Nessuna dipendenza da API esterne a pagamento o che richiedano connessione attiva, a meno che non sia l\'utente a richiederlo esplicitamente.

3. **Integrità dei Dati Video**:
   - I video originali non devono mai essere sovrascritti o cancellati per errore.
   - La concatenazione video deve privilegiare il flusso lossless senza ricodifica per preservare la qualità originale e completare l\'operazione in pochi secondi.

4. **Compatibilità Eseguibile (.exe con PyInstaller)**:
   - Qualsiasi percorso di file (configurazioni, icone, modelli Whisper) deve usare una funzione ausiliaria compatibile con sys._MEIPASS per funzionare sia in ambiente di sviluppo che all\'interno del pacchetto compilato .exe.
