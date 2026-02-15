# treehacks starter

## Structure
- `frontend/` Next.js (minimal UI)
- `backend/` FastAPI + OpenAI tool-calling agent + FFmpeg + action timeline

## Backend setup (Python)
1. `cd backend`
2. Create a venv and install deps:
   - `python -m venv venv`
   - `source venv/bin/activate`
   - `pip install -r requirements.txt`
3. Copy env: `cp .env.example .env` and set `OPENAI_API_KEY`
4. Set `JWT_SECRET` in `.env` (for auth)
5. Ensure `ffmpeg` is installed and on your PATH
6. Run: `./venv/bin/python -m uvicorn app:app --reload --port 8000 --env-file .env`

Endpoints:
- `POST /api/transform` (multipart form, field name `video`)
- `GET /media/original/*` and `GET /media/processed/*`
- `GET /media/analysis/*` (JSON action timeline)
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/me`
- `GET /api/videos`
- `GET /api/videos/{id}`

## Frontend setup (Next.js)
1. `cd frontend`
2. `npm install`
3. `npm run dev`

Optional: set `NEXT_PUBLIC_API_BASE` in `frontend/.env` (default `http://localhost:8000`).

## Notes
- The OpenAI tool-calling agent lives in `backend/ai_agents/agent.py` and always calls `speed_up_video`.
- The video processing logic is isolated in `backend/ai_agents/video.py`.
- Action timeline extraction is in `backend/ai_agents/action_timeline.py` and uses a VLM + optional audio transcription.
- If you want timestamped audio segments, set `OPENAI_ASR_MODEL=whisper-1` (it supports `verbose_json` segments).
- The backend now also generates a couple of random edit variants (combos) and returns them in `variants`.
- For faster video processing on macOS, set `VIDEO_HWACCEL=videotoolbox` and `VIDEO_ENCODER=h264_videotoolbox`.
- You can reduce analysis cost with `ACTION_FPS` and `ACTION_FRAME_SCALE`.
- GPU-heavy generative workflows live in `backend/ai_agents/generative/` (background replace, object erase, text replace) and are triggered via an agent that writes job specs.
- GPU dependencies for those workflows are listed in `backend/ai_agents/generative/requirements-gpu.txt`.
- Text overlays require an ffmpeg build with the `drawtext` filter (libfreetype).
