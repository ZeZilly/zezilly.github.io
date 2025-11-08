# Agent Ingest MVP (Private → OSS)

Strong starter to ingest allowed YouTube links, queue background jobs, and prepare for transcription and vector indexing.

IMPORTANT: Legal notice
- Only process content you own, have explicit permission for, or clearly licensed for reuse (e.g., Creative Commons).
- Respect YouTube Terms of Service and applicable copyright laws.

## Prerequisites (macOS)
- Homebrew
- Python 3.11+
- Docker Desktop (for Docker + Compose)
- ffmpeg (yt-dlp audio extraction)

Install prerequisites:

```
brew install ffmpeg
```

## Setup

1) Clone and create environment
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

2) Start infra (Redis, Qdrant)
```
docker-compose up -d
```

3) Run API and worker
```
uvicorn app.main:app --reload --port 8000
# new terminal
source .venv/bin/activate
python worker.py
```

## Test

Ingest a video you have rights to process:
```
curl -X POST http://localhost:8000/ingest \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=YOUR_VIDEO","confirm_rights":true}'
```

Check job status:
```
curl http://localhost:8000/jobs/<JOB_ID>
```

Artifacts are written to `data/<timestamp>/` with a `manifest.json` and downloaded `audio.m4a`.

## Admin Panel (GitHub Pages)

This repo includes a minimal admin UI under `frontend/` that can be deployed on GitHub Pages (free). It is a static site that calls your backend API and uses SSE for live updates.

1) Locally develop UI
```
cd frontend
npm ci
npm run dev
```

2) Configure API base URL for deployment
- Set a repository Variable named `API_BASE_URL` to your backend public URL (e.g., `https://your-tunnel.example.com`). The GitHub Actions workflow will inject it as `VITE_API_BASE_URL` at build time.

3) Deploy to Pages
- Enable GitHub Pages in repo Settings → Pages → Build and deployment: Source = GitHub Actions.
- Push to `main` and the workflow `.github/workflows/gh-pages.yml` will build and publish.

Notes:
- GitHub Pages is static; for “real-time” the UI subscribes to a Server-Sent Events endpoint exposed by FastAPI (`/jobs/{id}/stream`).
- Your backend must be reachable over the Internet. For free tunneling options, see below.

## Expose Backend Publicly (Free options)

- Cloudflare Tunnel (free): Securely expose `http://localhost:8000` without opening ports.
- Ngrok (free tier): `ngrok http 8000`.
- Render/Fly.io/ Railway free tiers: deploy FastAPI + Redis if needed.

Update `API_BASE_URL` accordingly so the Pages UI can reach your backend.

## Admin Panel Features

- Start ingest jobs from UI
- Live status via SSE
- Job actions: Trigger n8n workflow, Cancel job
- Settings:
  - Toggle and set n8n webhook URL
  - Toggle and set Telegram bot token + chat id
  - Test integrations (ping) and send Telegram test
  - Auto trigger n8n on job finish (client-side)
- Integrations info tab with guidance for WhatsApp/Instagram via n8n

Security note: Do not expose secrets in the frontend for production. Use backend-side storage and server-side calls.

## n8n (Free visual workflow)

Docker Compose includes an `n8n` service on `http://localhost:5678`.
- Create a Webhook trigger in n8n (e.g., `POST /webhook/after-job`).
- From worker steps, you can `POST` results to that webhook to fan-out automations (publish, notify, etc.).
- For public access, also tunnel/host n8n.

Example integration idea:
- On job finish, call n8n Webhook with manifest path → n8n continues: transcription → summarization → publish.

### Telegram notifications (optional)

Configure in Admin → Settings:
- enable Telegram, set `bot token` and `chat id`.
- Use "Test" to verify. The backend calls Telegram API server-side.

## Next steps
- Add transcription with WhisperX or faster-whisper
- Add embeddings + Qdrant collection management
- Add React-Admin frontend (jobs list + details)
- Add Prometheus metrics and Grafana dashboards
- Harden security: auth, rate limits, API keys, logging

## Notes
- ffmpeg must be available in PATH for yt-dlp audio extraction.
- `.env` values override defaults (see `.env.example`).
