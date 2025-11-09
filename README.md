# kd-pdf-to-mp (Render-ready)

A minimal Flask web service to submit PDFs to Mathpix and retrieve the converted Markdown. Built for deployment on Render.

## Endpoints

- `GET /health`
  - Returns service status and whether required env vars are present.
- `POST /process`
  - Multipart form upload with field `file` (PDF). Optional `options` form field (JSON) to override Mathpix options.
  - Returns `{ pdf_id, status_url, download_url }`.
- `GET /status/<pdf_id>`
  - Proxies Mathpix job status response.
- `GET /download/<pdf_id>.md`
  - Downloads the converted Markdown when the job has completed.

## Environment variables

Set these with your Mathpix credentials (do NOT commit secrets):

- `MATHPIX_APP_ID`
- `MATHPIX_APP_KEY`

Create a local `.env` from the example if you want:

```
cp .env.example .env
```

## Local development

1. Python 3.10+ recommended.
2. Install deps:

```bash
pip install -r requirements.txt
```

3. Set env vars (PowerShell example):

```powershell
$env:MATHPIX_APP_ID="your_app_id"; $env:MATHPIX_APP_KEY="your_app_key"
```

4. Run locally:

```bash
python server.py
```

Then open http://localhost:5000/health

## Deploy to Render

- Push this repo to GitHub.
- Create a new Web Service on Render and choose "Use render.yaml" or point it to this repo. Render will auto-detect the `render.yaml` and apply the config:
  - Build: `pip install -r requirements.txt`
  - Start: `gunicorn server:app -b 0.0.0.0:$PORT`
- Add environment variables `MATHPIX_APP_ID` and `MATHPIX_APP_KEY` in the service settings.

## Notes

- This service does not store files. Upload a PDF, receive a `pdf_id`, poll `/status`, and download Markdown via `/download` when ready.
- For large or long-running jobs, prefer polling from the client. Avoid long synchronous waits in a single request on Render.
