# TECHAM Replay Sync 0.2.2

Correzioni: la coda offline non puo sovrascrivere salvataggi concorrenti; un invio riuscito elimina i dati precedenti dello stesso contenuto; i completamenti in coda restano conservati; il primo errore di rete interrompe il tentativo di svuotamento senza perdere il resto della coda. Il cambio file senza metadati non eredita il titolo precedente. Polling e notifiche di fine riproduzione sono serializzati.

Verifica locale: python tests/sync-regressions.py <cartella-addon-estratta>. Test con API Kodi simulate: coda vecchia, completamento, retry limitato, flush concorrente, nuovo titolo non riconosciuto, sintassi Python. Nessuna prova con l'account reale o riproduzione Kodi su TV in questa release; la correzione del sintomo specifico va confermata sul dispositivo. Restano necessari account collegato e identificativi TMDb del contenuto.
