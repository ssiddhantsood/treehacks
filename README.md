# treehacks starter

## Structure
- `frontend/` Next.js (minimal UI)
- `backend/` FastAPI + OpenAI tool-calling agent + FFmpeg + action timeline

## Backend setup (Python)
1. `cd backend`
2. Create a virtualenv and install deps: `pip install -r requirements.txt`
3. Copy env: `cp .env.example .env` and set `OPENAI_API_KEY`
4. Ensure `ffmpeg` is installed and on your PATH
5. Run: `uvicorn app:app --reload --port 8000`

Endpoints:
- `POST /api/transform` (multipart form, field name `video`)
- `GET /media/original/*` and `GET /media/processed/*`
- `GET /media/analysis/*` (JSON action timeline)

## Frontend setup (Next.js)
1. `cd frontend`
2. `npm install`
3. `npm run dev`

Optional: set `NEXT_PUBLIC_API_BASE` in `frontend/.env` (default `http://localhost:8000`).

## Notes
- The OpenAI tool-calling agent lives in `backend/agent.py` and always calls `speed_up_video`.
- The video processing logic is isolated in `backend/video.py`.
- Action timeline extraction is in `backend/action_timeline.py` and uses a VLM + optional audio transcription.
- If you want timestamped audio segments, set `OPENAI_ASR_MODEL=whisper-1` (it supports `verbose_json` segments).
