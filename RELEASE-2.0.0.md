# TECHAM Replay Sync 2.0.0

Release principale dell'integrazione tra TECHAM Replay e Kodi.

## Novità

- Replay Hub in Kodi: Continua a guardare, libreria personale e attività recente.
- Comando **Sincronizza ora** dal profilo web e conferma dell'esito sul dispositivo.
- Stato dispositivo esteso con versione add-on, profilo Kodi, ultimo allineamento ed eventuale errore.
- Associazione manuale TMDb per film e serie che non espongono un identificativo compatibile.
- Cronologia locale delle ultime 50 sincronizzazioni e diagnostica degli elementi non associati.
- Scansione JSON-RPC paginata per librerie Kodi di grandi dimensioni.
- Heartbeat compatibile con i nomi personalizzati scelti sul sito.

## Compatibilità e aggiornamento

- Aggiornamento diretto dalla 1.4.0 tramite il repository esistente.
- Compatibile con Kodi 19, 20, 21 e 22 e con Python 3.
- Token dispositivo, coda offline, impostazioni e stato locale vengono mantenuti.
- Il database riceve soltanto colonne additive: i dispositivi già collegati restano validi.

## Sicurezza e contenuti

L'add-on non distribuisce video né aggira pubblicità o protezioni. Replay Hub apre esclusivamente contenuti già presenti nella libreria locale di Kodi.

## Integrità

SHA-256 di `plugin.video.techamreplay-2.0.0.zip`:

`2f0ca5ad7671ec90967fe95126dc170e0700218c4141c7560c284ccd2dbf52ee`
