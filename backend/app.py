import asyncio
import os
import shutil
import random
import traceback
from typing import Annotated
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent import COMBOS, run_combo_agent, run_speedup_agent
from action_timeline import analyze_video
from auth import create_access_token, decode_token, hash_password, verify_password
from db import (
    add_variant,
    create_user,
    create_video,
    get_user_by_email,
    get_user_by_id,
    get_video_with_variants,
    init_db,
    list_videos_for_user,
)

load_dotenv()

DEBUG = os.getenv("DEBUG", "0") == "1"
VARIANT_CONCURRENCY = int(os.getenv("VIDEO_VARIANT_CONCURRENCY", "1") or "1")

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

security = HTTPBearer()


def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload.get("sub", 0))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@app.get("/api/health")
async def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat()}


@app.on_event("startup")
async def on_startup():
    init_db()


@app.post("/api/auth/register")
async def register(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    if get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already registered")

    user = create_user(email, hash_password(password))
    token = create_access_token(user["id"])
    return {"ok": True, "token": token, "user": {"id": user["id"], "email": user["email"]}}


@app.post("/api/auth/login")
async def login(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user["id"])
    return {"ok": True, "token": token, "user": {"id": user["id"], "email": user["email"]}}


@app.get("/api/me")
async def me(user=Depends(get_current_user)):
    return {"ok": True, "user": {"id": user["id"], "email": user["email"]}}


@app.get("/api/videos")
async def list_videos(user=Depends(get_current_user)):
    return {"ok": True, "videos": list_videos_for_user(user["id"])}


@app.get("/api/videos/{video_id}")
async def get_video(video_id: str, user=Depends(get_current_user)):
    video = get_video_with_variants(video_id, user["id"])
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"ok": True, "video": video}


@app.post("/api/transform")
async def transform(video: UploadFile = File(...), user=Depends(get_current_user)):
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
    variants = []
    chosen_combos = []

    try:
        await asyncio.gather(
            run_in_threadpool(
                run_speedup_agent,
                str(original_path),
                str(processed_path),
                1.05,
            ),
            run_in_threadpool(
                analyze_video,
                str(original_path),
                str(analysis_path),
            ),
        )

        variants.append(
            {
                "name": "speed_up",
                "url": f"/media/processed/{processed_filename}",
            }
        )

        chosen_combos = random.sample(COMBOS, k=min(2, len(COMBOS)))
        if chosen_combos:
            concurrency = max(1, VARIANT_CONCURRENCY)
            semaphore = asyncio.Semaphore(concurrency)

            async def _run_variant(combo_name: str):
                async with semaphore:
                    variant_filename = f"{upload_id}-{combo_name}.mp4"
                    variant_path = PROCESSED_DIR / variant_filename
                    try:
                        await run_in_threadpool(
                            run_combo_agent,
                            str(original_path),
                            str(variant_path),
                            combo_name,
                        )
                        return {
                            "name": combo_name,
                            "url": f"/media/processed/{variant_filename}",
                        }
                    except Exception as exc:
                        if DEBUG:
                            print(f"Variant {combo_name} failed: {exc}")
                        return None

            results = await asyncio.gather(*[_run_variant(name) for name in chosen_combos])
            variants.extend([item for item in results if item])
    except Exception as exc:
        traceback.print_exc()
        detail = "Video processing failed"
        if DEBUG:
            detail = f"{type(exc).__name__}: {exc}"
        raise HTTPException(status_code=500, detail=detail) from exc

    original_url = f"/media/original/{original_filename}"
    analysis_url = f"/media/analysis/{analysis_filename}"

    create_video(
        upload_id,
        user["id"],
        original_url=original_url,
        analysis_url=analysis_url,
        metadata={
            "speedFactor": 1.05,
            "combos": chosen_combos,
        },
    )

    for variant in variants:
        add_variant(upload_id, variant["name"], variant["url"])

    return {
        "ok": True,
        "videoId": upload_id,
        "originalUrl": original_url,
        "processedUrl": f"/media/processed/{processed_filename}",
        "analysisUrl": analysis_url,
        "variants": variants,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
