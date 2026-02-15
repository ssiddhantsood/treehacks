import csv
import json
import os
import shutil
import traceback
from typing import Annotated
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import numpy as np
from openai import OpenAI

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
EMBEDDINGS_INPUT_TYPE = os.getenv("EMBEDDINGS_INPUT_TYPE", "CLUSTERING")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
OLDER_AUDIENCE_AGE = int(os.getenv("OLDER_AUDIENCE_AGE", "55") or "55")

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY") or "")

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


def _has_openai_env() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1).replace("```", "", 1)
    return cleaned.strip()


def _extract_json(text: str) -> dict:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        return {}
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                return {}
    return {}


def _truncate(text: str, limit: int = 180) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[:limit].rsplit(" ", 1)[0]
    return (trimmed or cleaned[:limit]).rstrip() + "..."


def _parse_age(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _top_terms(entries: list[str], limit: int = 4) -> list[str]:
    terms: list[str] = []
    for entry in entries:
        for chunk in entry.split(";"):
            cleaned = chunk.strip().lower()
            if cleaned:
                terms.append(cleaned)
    if not terms:
        return []
    counts = {}
    for term in terms:
        counts[term] = counts.get(term, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [item for item, _ in ranked[:limit]]


def _format_example(row: dict[str, str]) -> str:
    age = row.get("age") or ""
    gender = row.get("gender") or ""
    demo = row.get("demographic_info") or ""
    history = row.get("previous_search_history") or ""
    parts = []
    if age or gender:
        parts.append(", ".join([p for p in [age, gender] if p]))
    if demo:
        parts.append(demo)
    if history:
        shortened = history.strip()
        if len(shortened) > 80:
            shortened = shortened[:77].rsplit(" ", 1)[0] + "..."
        parts.append(shortened)
    return " | ".join([p for p in parts if p])


def _summarize_group_heuristic(members: list[dict[str, str]]) -> dict[str, object]:
    ages = [age for age in (_parse_age(m.get("age")) for m in members) if age is not None]
    avg_age = round(sum(ages) / len(ages)) if ages else None
    is_older = avg_age is not None and avg_age >= OLDER_AUDIENCE_AGE

    gender_counts: dict[str, int] = {}
    for member in members:
        gender = (member.get("gender") or "").strip().lower()
        if not gender:
            continue
        gender_counts[gender] = gender_counts.get(gender, 0) + 1
    top_genders = [g for g, _ in sorted(gender_counts.items(), key=lambda item: item[1], reverse=True)[:2]]

    demo_samples = []
    for member in members:
        demo = (member.get("demographic_info") or "").strip()
        if demo and demo not in demo_samples:
            demo_samples.append(demo)
        if len(demo_samples) >= 2:
            break

    interests = _top_terms([m.get("previous_search_history") or "" for m in members], limit=3)

    summary_parts = []
    if avg_age is not None:
        summary_parts.append(f"avg age {avg_age}")
    if top_genders:
        summary_parts.append(f"top genders: {', '.join(top_genders)}")
    if interests:
        summary_parts.append(f"interests: {', '.join(interests)}")
    if not summary_parts and demo_samples:
        summary_parts.append(f"demo: {demo_samples[0]}")
    summary = " · ".join(summary_parts) if summary_parts else "Mixed audience segment with diverse interests."
    summary = _truncate(summary, limit=260 if is_older else 200)

    example_limit = 3 if is_older else 2
    examples = [_truncate(ex, limit=120) for ex in (_format_example(m) for m in members[:example_limit]) if ex]
    return {
        "summary": summary,
        "traits": interests[:2],
        "examples": examples,
    }


def _summarize_group_llm(group_id: int, members: list[dict[str, str]]) -> dict[str, object] | None:
    if not _has_openai_env() or not members:
        return None

    sample_size = min(len(members), 20)
    samples = [_row_to_text(row) for row in members[:sample_size]]
    ages = [age for age in (_parse_age(m.get("age")) for m in members) if age is not None]
    avg_age = round(sum(ages) / len(ages)) if ages else None
    older_hint = avg_age is not None and avg_age >= OLDER_AUDIENCE_AGE
    summary_rule = "1-3 sentences"
    example_rule = "1-4 short examples"
    prompt = (
        "Summarize this audience cluster for an embeddings map. Focus on general trends and avoid listing every item. "
        f"Return JSON only with keys: summary ({summary_rule}), traits (2-4 short phrases), examples ({example_rule}). "
        "Examples should be short fragments derived from the input, not long lists.\n"
        f"Cluster {group_id} has {len(members)} profiles."
        + (f" Average age is ~{avg_age}." if avg_age is not None else "")
        + (
            f" Guidance: average age >= {OLDER_AUDIENCE_AGE} often benefits from slightly more detail and extra examples."
            if older_hint
            else " Guidance: if the audience skews younger or attention is short, keep the summary tight."
        )
        + " Sample profiles:\n- "
        + "\n- ".join(samples)
    )

    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You summarize audience clusters for UI tooltips. Be concise and trend-focused."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
    except Exception:
        return None

    content = response.choices[0].message.content or ""
    data = _extract_json(content)
    if not data:
        return None

    summary = _truncate(str(data.get("summary") or "").strip(), limit=260)
    traits = data.get("traits") or []
    if isinstance(traits, str):
        traits = [t.strip() for t in traits.split(",") if t.strip()]
    if not isinstance(traits, list):
        traits = []
    traits = [_truncate(str(item).strip(), limit=40) for item in traits if str(item).strip()]

    examples = data.get("examples") or []
    if isinstance(examples, str):
        examples = [ex.strip() for ex in examples.split(";") if ex.strip()]
    if not isinstance(examples, list):
        examples = []
    examples = [_truncate(str(item).strip(), limit=120) for item in examples if str(item).strip()]

    if not summary:
        return None

    return {
        "summary": summary,
        "traits": traits[:4],
        "examples": examples[:4],
    }


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


def _project_nd(vectors: np.ndarray, dims: int) -> np.ndarray:
    if vectors.size == 0:
        return np.zeros((0, dims), dtype=np.float32)
    if vectors.shape[0] == 1:
        return np.full((1, dims), 0.5, dtype=np.float32)
    centered = vectors - vectors.mean(axis=0, keepdims=True)
    if centered.shape[1] == 1:
        coords = np.concatenate(
            [centered] + [np.zeros((centered.shape[0], 1), dtype=np.float32) for _ in range(dims - 1)],
            axis=1,
        )
    else:
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        components = vt[:dims].T
        coords = centered @ components
        if coords.shape[1] < dims:
            coords = np.concatenate(
                [coords, np.zeros((coords.shape[0], dims - coords.shape[1]), dtype=np.float32)], axis=1
            )
    return coords.astype(np.float32)


def _normalize_points(coords: np.ndarray) -> np.ndarray:
    if coords.size == 0:
        return coords
    if coords.shape[0] == 1:
        return np.full_like(coords, 0.5)
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
async def get_embeddings(
    video_id: str,
    group_count: int | None = Query(None, alias="groupCount"),
    user=Depends(get_current_user),
):
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
    group_count = _coerce_int(group_count) or _coerce_int(metadata.get("groupCount")) or 3
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

    coords = _project_nd(vectors, 3)
    normalized = _normalize_points(coords)
    labels, _ = _kmeans(vectors, group_count)

    points = []
    grouped_rows: dict[int, list[dict[str, str]]] = {}
    for idx, row in enumerate(rows):
        summary = ", ".join(
            [
                row.get("age", "") or "",
                row.get("gender", "") or "",
                row.get("demographic_info", "") or "",
            ]
        ).strip(" ,")
        group_id = int(labels[idx])
        grouped_rows.setdefault(group_id, []).append(row)
        points.append(
            {
                "x": round(float(normalized[idx][0]), 5),
                "y": round(float(normalized[idx][1]), 5),
                "z": round(float(normalized[idx][2]), 5),
                "groupId": group_id,
                "index": idx,
                "summary": summary,
            }
        )

    groups = []
    for group_id in sorted(grouped_rows.keys()):
        members = grouped_rows[group_id]
        llm_summary = await run_in_threadpool(_summarize_group_llm, group_id, members)
        summary_data = llm_summary or _summarize_group_heuristic(members)
        groups.append(
            {
                "groupId": group_id,
                "label": f"Group {group_id}",
                "summary": summary_data.get("summary"),
                "traits": summary_data.get("traits"),
                "examples": summary_data.get("examples"),
                "memberCount": len(members),
                "source": "llm" if llm_summary else "heuristic",
            }
        )

    return {"ok": True, "points": points, "count": len(points), "source": source, "groups": groups}


@app.post("/api/transform")
async def transform(
    video: UploadFile = File(...),
    profiles: UploadFile | None = File(None),
    name: str | None = Form(None),
    product_desc: str | None = Form(None),
    goal: str | None = Form(None),
    group_count: int | None = Form(None, alias="groupCount"),
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

    analysis_filename = f"{upload_id}.json"
    analysis_path = ANALYSIS_DIR / analysis_filename
    variants = []

    analysis_result = None

    try:
        analysis_task = run_in_threadpool(
            analyze_video,
            str(original_path),
            str(analysis_path),
        )
        analysis_result = await analysis_task
    except Exception as exc:
        traceback.print_exc()
        detail = "Video processing failed"
        if DEBUG:
            detail = f"{type(exc).__name__}: {exc}"
        raise HTTPException(status_code=500, detail=detail) from exc

    original_url = f"/media/original/{original_filename}"
    analysis_url = f"/media/analysis/{analysis_filename}"

    metadata_payload = {}
    if product_desc:
        metadata_payload["productDesc"] = product_desc
    if goal:
        metadata_payload["goal"] = goal
    if _coerce_int(group_count):
        metadata_payload["groupCount"] = int(group_count)
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

    return {
        "ok": True,
        "videoId": upload_id,
        "name": name,
        "originalUrl": original_url,
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
