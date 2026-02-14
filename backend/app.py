import os
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent import run_speedup_agent
from action_timeline import analyze_video

load_dotenv()

DEBUG = os.getenv("DEBUG", "0") == "1"

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
TMP_DIR = STORAGE_DIR / "tmp"
ORIGINAL_DIR = STORAGE_DIR / "original"
PROCESSED_DIR = STORAGE_DIR / "processed"
ANALYSIS_DIR = STORAGE_DIR / "analysis"

for folder in (TMP_DIR, ORIGINAL_DIR, PROCESSED_DIR, ANALYSIS_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/media/original", StaticFiles(directory=str(ORIGINAL_DIR)), name="original")
app.mount("/media/processed", StaticFiles(directory=str(PROCESSED_DIR)), name="processed")
app.mount("/media/analysis", StaticFiles(directory=str(ANALYSIS_DIR)), name="analysis")


@app.get("/api/health")
async def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


@app.post("/api/transform")
async def transform(video: UploadFile = File(...)):
    if not video:
        raise HTTPException(status_code=400, detail="No file uploaded")

    upload_id = uuid4().hex
    suffix = Path(video.filename or "").suffix or ".mp4"
    original_filename = f"{upload_id}{suffix}"
    original_path = ORIGINAL_DIR / original_filename

    with original_path.open("wb") as buffer:
        shutil.copyfileobj(video.file, buffer)

    await video.close()

    processed_filename = f"{upload_id}-speed.mp4"
    processed_path = PROCESSED_DIR / processed_filename

    analysis_filename = f"{upload_id}.json"
    analysis_path = ANALYSIS_DIR / analysis_filename

    try:
        await run_in_threadpool(
            run_speedup_agent,
            str(original_path),
            str(processed_path),
            1.05,
        )
        await run_in_threadpool(
            analyze_video,
            str(original_path),
            str(analysis_path),
        )
    except Exception as exc:
        traceback.print_exc()
        detail = "Video processing failed"
        if DEBUG:
            detail = f"{type(exc).__name__}: {exc}"
        raise HTTPException(status_code=500, detail=detail) from exc

    return {
        "ok": True,
        "originalUrl": f"/media/original/{original_filename}",
        "processedUrl": f"/media/processed/{processed_filename}",
        "analysisUrl": f"/media/analysis/{analysis_filename}",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
