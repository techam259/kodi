# TECHAM Replay Sync 1.0.0

Prima versione stabile dell'add-on Kodi.

## Esperienza su Kodi

- collegamento con codice direttamente da **Add-on programmi → TECHAM Replay Sync**;
- disconnessione con revoca sul server e fallback locale esplicito;
- pannello con versione, dispositivo, stato API, coda, ultimo tentativo, ultima operazione ed errori;
- test della connessione tramite endpoint dedicato al dispositivo;
- notifica su Kodi mostrata una sola volta dopo ogni aggiornamento;
- sezione **Novità della versione** sempre consultabile dal pannello dell'add-on;
- icona ufficiale TECHAM Replay nel catalogo Kodi.

## Affidabilità e sicurezza

- i token vengono inviati soltanto a endpoint HTTPS validi;
- i token revocati o scaduti vengono rimossi localmente;
- gli avanzamenti non inviati restano in coda durante il nuovo collegamento;
- il codice monouso viene consumato atomicamente per impedire un doppio utilizzo;
- un dispositivo può essere revocato sia da Kodi sia dal profilo web;
- la coda resta deduplicata, serializzata e limitata a 100 elementi.

## Riproduzione

- sincronizzazione di film ed episodi da libreria Kodi e add-on con metadati TMDb;
- compatibilità mantenuta con Stream4Me;
- supporto agli episodi speciali TMDb della stagione 0;
- protezione contro il completamento errato dell'episodio successivo;
- ripresa tra dispositivi e soglia di completamento configurabile.

## Verifica richiesta prima del rilascio

- test Python sulla sorgente e sullo ZIP estratto;
- lint e build di produzione del sito Replay;
- validazione XML, struttura ZIP e checksum repository;
- confronto tra bytes locali e bytes pubblici dopo l'unico deploy;
- prova finale su Kodi 21.3 con account reale.
