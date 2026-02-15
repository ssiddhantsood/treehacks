import asyncio
import csv
import json
import os
import random
import shutil
import traceback
from typing import Annotated
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import numpy as np

from ai_agents.agent import COMBOS, run_combo_agent, run_speedup_agent
from ai_agents.action_timeline import analyze_video
from ai_agents.group_ads import generate_group_variants
from ai_agents.market_research import run_market_research_agent
from auth import create_access_token, decode_token, hash_password, verify_password
from db import (
    add_variant,
    create_user,
    create_video,
    delete_variants_by_prefix,
    delete_video,
    get_user_by_email,
    get_user_by_id,
    get_video_with_variants,
    init_db,
    list_videos_for_user,
    update_video_analysis_url,
    update_video_metadata,
)
from cluster_profiles import _embed_texts, _kmeans

load_dotenv()

DEBUG = os.getenv("DEBUG", "0") == "1"
VARIANT_CONCURRENCY = int(os.getenv("VIDEO_VARIANT_CONCURRENCY", "1") or "1")
EMBEDDINGS_INPUT_TYPE = os.getenv("EMBEDDINGS_INPUT_TYPE", "CLUSTERING")

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
TMP_DIR = STORAGE_DIR / "tmp"
ORIGINAL_DIR = STORAGE_DIR / "original"
PROCESSED_DIR = STORAGE_DIR / "processed"
ANALYSIS_DIR = STORAGE_DIR / "analysis"
PROFILES_DIR = STORAGE_DIR / "profiles"

for folder in (TMP_DIR, ORIGINAL_DIR, PROCESSED_DIR, ANALYSIS_DIR, PROFILES_DIR):
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


def _coerce_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_embedding_env() -> bool:
    return bool(
        os.getenv("ELASTICSEARCH_ENDPOINT")
        and os.getenv("ELASTIC_API_KEY")
        and os.getenv("ELASTIC_INFERENCE_ID")
    )


def _load_profile_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f)]


def _row_to_text(row: dict[str, str]) -> str:
    return (
        f"age: {row.get('age', '')}; "
        f"gender: {row.get('gender', '')}; "
        f"demographic: {row.get('demographic_info', '')}; "
        f"previous_search_history: {row.get('previous_search_history', '')}"
    )


def _simple_profile_vectors(rows: list[dict[str, str]]) -> np.ndarray:
    vectors = []
    for row in rows:
        age_raw = row.get("age") or ""
        try:
            age = float(age_raw)
        except ValueError:
            age = 0.0
        gender = (row.get("gender") or "").strip().lower()
        if gender.startswith("m"):
            gender_val = 1.0
        elif gender.startswith("f"):
            gender_val = -1.0
        else:
            gender_val = 0.0
        demo = (row.get("demographic_info") or "")
        history = (row.get("previous_search_history") or "")
        demo_len = len(demo) / 100.0
        history_len = len(history) / 100.0
        interest_count = max(1, len([c for c in history.split(";") if c.strip()])) / 10.0
        vectors.append([age / 100.0, gender_val, demo_len, history_len, interest_count])
    return np.array(vectors, dtype=np.float32)


def _project_2d(vectors: np.ndarray) -> np.ndarray:
    if vectors.size == 0:
        return np.zeros((0, 2), dtype=np.float32)
    if vectors.shape[0] == 1:
        return np.array([[0.5, 0.5]], dtype=np.float32)
    centered = vectors - vectors.mean(axis=0, keepdims=True)
    if centered.shape[1] == 1:
        coords = np.concatenate([centered, np.zeros((centered.shape[0], 1), dtype=np.float32)], axis=1)
    else:
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        components = vt[:2].T
        coords = centered @ components
    return coords.astype(np.float32)


def _normalize_points(coords: np.ndarray) -> np.ndarray:
    if coords.size == 0:
        return coords
    mins = coords.min(axis=0)
    maxs = coords.max(axis=0)
    span = np.where(maxs - mins == 0, 1.0, maxs - mins)
    return (coords - mins) / span


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


@app.delete("/api/videos/{video_id}")
async def delete_video_route(video_id: str, user=Depends(get_current_user)):
    video = get_video_with_variants(video_id, user["id"])
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    original_url = video.get("originalUrl") or ""
    analysis_url = video.get("analysisUrl") or ""
    variant_urls = [variant.get("url") for variant in (video.get("variants") or []) if variant.get("url")]

    def _safe_unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except Exception:
            return

    if original_url:
        _safe_unlink(ORIGINAL_DIR / Path(original_url).name)
    if analysis_url:
        _safe_unlink(ANALYSIS_DIR / Path(analysis_url).name)
    for url in variant_urls:
        _safe_unlink(PROCESSED_DIR / Path(url).name)

    profiles_path = PROFILES_DIR / f"{video_id}.csv"
    _safe_unlink(profiles_path)

    delete_video(video_id, user["id"])
    return {"ok": True}


@app.get("/api/videos/{video_id}/embeddings")
async def get_embeddings(video_id: str, user=Depends(get_current_user)):
    video = get_video_with_variants(video_id, user["id"])
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    profiles_path = PROFILES_DIR / f"{video_id}.csv"
    if not profiles_path.exists():
        raise HTTPException(status_code=404, detail="Profiles not found")

    rows = _load_profile_rows(profiles_path)
    if not rows:
        return {"ok": True, "points": [], "count": 0}

    metadata = video.get("metadata") or {}
    group_count = _coerce_int(metadata.get("groupCount")) or 3
    group_count = max(1, min(group_count, len(rows)))

    if _has_embedding_env():
        texts = [_row_to_text(row) for row in rows]
        embeddings = _embed_texts(
            texts,
            endpoint=os.getenv("ELASTICSEARCH_ENDPOINT") or "",
            api_key=os.getenv("ELASTIC_API_KEY") or "",
            inference_id=os.getenv("ELASTIC_INFERENCE_ID") or "",
            input_type=EMBEDDINGS_INPUT_TYPE,
        )
        vectors = np.array(embeddings, dtype=np.float32)
        source = "embeddings"
    else:
        vectors = _simple_profile_vectors(rows)
        source = "heuristic"

    coords = _project_2d(vectors)
    normalized = _normalize_points(coords)
    labels, _ = _kmeans(vectors, group_count)

    points = []
    for idx, row in enumerate(rows):
        summary = ", ".join(
            [
                row.get("age", "") or "",
                row.get("gender", "") or "",
                row.get("demographic_info", "") or "",
            ]
        ).strip(" ,")
        points.append(
            {
                "x": round(float(normalized[idx][0]), 5),
                "y": round(float(normalized[idx][1]), 5),
                "groupId": int(labels[idx]),
                "index": idx,
                "summary": summary,
            }
        )

    return {"ok": True, "points": points, "count": len(points), "source": source}


@app.post("/api/transform")
async def transform(
    video: UploadFile = File(...),
    profiles: UploadFile | None = File(None),
    name: str | None = Form(None),
    product_desc: str | None = Form(None),
    goal: str | None = Form(None),
    user=Depends(get_current_user),
):
    if not video:
        raise HTTPException(status_code=400, detail="No file uploaded")

    upload_id = uuid4().hex
    suffix = Path(video.filename or "").suffix or ".mp4"
    original_filename = f"{upload_id}{suffix}"
    original_path = ORIGINAL_DIR / original_filename

    with original_path.open("wb") as buffer:
        shutil.copyfileobj(video.file, buffer)

    await video.close()

    if profiles:
        profiles_suffix = Path(profiles.filename or "").suffix.lower()
        if profiles_suffix and profiles_suffix != ".csv":
            raise HTTPException(status_code=400, detail="Profiles file must be a CSV")
        profiles_path = PROFILES_DIR / f"{upload_id}.csv"
        with profiles_path.open("wb") as buffer:
            shutil.copyfileobj(profiles.file, buffer)
        await profiles.close()

    processed_filename = f"{upload_id}-speed.mp4"
    processed_path = PROCESSED_DIR / processed_filename

    analysis_filename = f"{upload_id}.json"
    analysis_path = ANALYSIS_DIR / analysis_filename
    variants = []
    chosen_combos = []

    analysis_result = None

    try:
        speed_task = run_in_threadpool(
            run_speedup_agent,
            str(original_path),
            str(processed_path),
        )
        analysis_task = run_in_threadpool(
            analyze_video,
            str(original_path),
            str(analysis_path),
        )
        _, analysis_result = await asyncio.gather(speed_task, analysis_task)

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

    metadata_payload = {
        "speedFactor": 1.05,
        "combos": chosen_combos,
    }
    if product_desc:
        metadata_payload["productDesc"] = product_desc
    if goal:
        metadata_payload["goal"] = goal
    if isinstance(analysis_result, dict):
        metadata_payload["analysis"] = {
            "perSecondDescriptions": analysis_result.get("per_second_descriptions", []),
            "sceneSegments": analysis_result.get("scene_segments", []),
            "justificationTimeline": analysis_result.get("justification_timeline", []),
        }

    create_video(
        upload_id,
        user["id"],
        original_url=original_url,
        analysis_url=analysis_url,
        metadata=metadata_payload,
        name=name,
    )

    for variant in variants:
        add_variant(upload_id, variant["name"], variant["url"])

    return {
        "ok": True,
        "videoId": upload_id,
        "name": name,
        "originalUrl": original_url,
        "processedUrl": f"/media/processed/{processed_filename}",
        "analysisUrl": analysis_url,
        "variants": variants,
    }


@app.post("/api/videos/{video_id}/generate-ads")
async def generate_ads(video_id: str, payload: dict | None = None, user=Depends(get_current_user)):
    payload = payload or {}
    group_count = _coerce_int(payload.get("groupCount") or payload.get("group_count"))
    max_edits = _coerce_int(payload.get("maxEdits") or payload.get("max_edits"))

    video = get_video_with_variants(video_id, user["id"])
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    original_url = video.get("originalUrl")
    if not original_url:
        raise HTTPException(status_code=400, detail="Video has no original asset")

    original_path = ORIGINAL_DIR / Path(original_url).name
    if not original_path.exists():
        raise HTTPException(status_code=404, detail="Original video file missing")

    analysis_data = None
    analysis_url = video.get("analysisUrl")
    if analysis_url:
        analysis_path = ANALYSIS_DIR / Path(analysis_url).name
        if analysis_path.exists():
            try:
                analysis_data = json.loads(analysis_path.read_text())
            except json.JSONDecodeError:
                analysis_data = None

    if analysis_data is None:
        analysis_filename = f"{video_id}.json"
        analysis_path = ANALYSIS_DIR / analysis_filename
        analysis_data = await run_in_threadpool(
            analyze_video,
            str(original_path),
            str(analysis_path),
        )
        analysis_url = f"/media/analysis/{analysis_filename}"
        update_video_analysis_url(video_id, user["id"], analysis_url)

    profiles_path = PROFILES_DIR / f"{video_id}.csv"
    csv_path = str(profiles_path) if profiles_path.exists() else str(BASE_DIR / "mock_profiles.csv")

    try:
        variants, group_metadata = await run_in_threadpool(
            generate_group_variants,
            video_id,
            original_path,
            analysis_data,
            PROCESSED_DIR,
            csv_path,
            group_count,
            max_edits,
        )
    except Exception as exc:
        traceback.print_exc()
        detail = "Ad generation failed"
        if DEBUG:
            detail = f"{type(exc).__name__}: {exc}"
        raise HTTPException(status_code=500, detail=detail) from exc

    delete_variants_by_prefix(video_id, "group-")
    for variant in variants:
        add_variant(video_id, variant["name"], variant["url"])

    metadata = video.get("metadata") or {}
    metadata["groupVariants"] = group_metadata
    metadata["groupCount"] = len(group_metadata)
    metadata["generatedAt"] = datetime.now(timezone.utc).isoformat()
    update_video_metadata(video_id, user["id"], metadata)

    return {
        "ok": True,
        "variants": variants,
        "metadata": metadata,
        "analysisUrl": analysis_url,
    }


@app.post("/api/market-research")
async def market_research(payload: dict, user=Depends(get_current_user)):
    description = (payload.get("description") or payload.get("audienceDescription") or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="description is required")

    product = payload.get("product")
    region = payload.get("region")
    goal = payload.get("goal")
    extra_focus = payload.get("extraFocus") or payload.get("extra_focus")
    language = payload.get("language")

    result = await run_in_threadpool(
        run_market_research_agent,
        description,
        product,
        region,
        goal,
        extra_focus,
        language,
    )

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Market research failed"))

    return {"ok": True, "result": result}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
