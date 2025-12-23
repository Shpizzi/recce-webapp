# Recce Webapp

Webapp minimalista basata su Streamlit che orchestra lo scraping da Rallymaps (via Node + Puppeteer) e la conversione GPX → KML (via `curve_detector.py`). L’utente finale incolla un link Rallymaps, preme **Genera KML** e scarica automaticamente `KML_ALL.zip`.

## Componenti principali
- **Streamlit UI (`app.py`)**: gestisce i job, crea cartelle `work/<job_id>/…`, mostra log e fornisce il download dello ZIP finale.
- **Node (`rally2gpx/index_all.js`)**: versione non interattiva derivata da rally2gpx che genera un GPX per ogni stage all’interno di `work/<job_id>/Desktop`.
- **Python (`curve_detector.py`)**: converte ogni GPX in KML salvandolo in `work/<job_id>/kml` (placeholder da sostituire con lo script reale fornito dall’utente).

## Sostituire `curve_detector.py`
1. Cancella il file placeholder esistente (`curve_detector.py`).
2. Copia lo script reale `curve_detector.py` nella root del progetto.
3. Assicurati che lo script accetti la CLI `python3 curve_detector.py input.gpx output.kml` (come già previsto dall’implementazione corrente).

## Cartella `rally2gpx`
In questa repo `rally2gpx/package.json` e `package-lock.json` sono placeholder minimi. Per un funzionamento completo conviene copiare l’intero progetto originale `rally2gpx` (con le sue dipendenze reali) dentro `recce-webapp/rally2gpx/`, mantenendo **il file `index.js` esattamente uguale al sorgente qui incluso** e aggiungendo `index_all.js` (già presente). Dopo la copia, riesegui `npm install` o `npm ci` nella sottocartella.

## Requisiti locali
- Docker (per eseguire l’app senza configurare manualmente Python/Node)
- OPPURE Python 3.11 + Node 20 + dipendenze del progetto `rally2gpx`

## Esecuzione locale via Docker
```bash
docker build -t recce-webapp .
docker run --rm -p 8501:8501 recce-webapp
```
Poi apri `http://localhost:8501` nel browser.

## Deploy su Render (Docker Web Service)
1. Push della cartella su un repository git.
2. Crea un nuovo **Web Service** su Render scegliendo “Deploy an existing image/ Dockerfile”.
3. Imposta la repo e il branch.
4. Usa il comando di avvio di default del Dockerfile (`streamlit run app.py --server.port=8501 --server.address=0.0.0.0`).
5. Configura una variabile di ambiente `STREAMLIT_SERVER_PORT=8501` solo se necessario.
6. Effettua il deploy; Render costruirà automaticamente l’immagine usando il Dockerfile incluso.

## Troubleshooting Puppeteer
- Verifica che nel container sia presente Chromium/Chrome. Il Dockerfile installa le librerie richieste; se Puppeteer richiede Chromium aggiuntivo, imposta `PUPPETEER_EXECUTABLE_PATH` verso il binario installato o rimuovi `PUPPETEER_SKIP_CHROMIUM_DOWNLOAD`.
- Se lo scraping fallisce per problemi di cookie/consenso, controlla `work/<job_id>/logs/rally2gpx.log` dall’interfaccia Streamlit.
- Assicurati che il server abbia abbastanza RAM/CPU perché Puppeteer necessita di Chromium headless.

## Struttura cartelle generata
```
recce-webapp/
├─ app.py
├─ curve_detector.py               # placeholder → sostituire
├─ rally2gpx/
│  ├─ index.js                     # sorgente originale (fornito qui)
│  ├─ index_all.js                 # versione non interattiva/multi-stage
│  ├─ package.json                 # placeholder → sostituire con quello reale
│  └─ package-lock.json            # placeholder → sostituire con quello reale
├─ requirements.txt
├─ Dockerfile
├─ README.md
└─ work/                           # generata a runtime, ignorata da git
```
