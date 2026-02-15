import json
import os
from pathlib import Path
from uuid import uuid4

from auth import hash_password
from db import (
    add_variant,
    create_user,
    create_video,
    get_user_by_email,
    list_videos_for_user,
)

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
ORIGINAL_DIR = STORAGE_DIR / "original"
PROCESSED_DIR = STORAGE_DIR / "processed"
ANALYSIS_DIR = STORAGE_DIR / "analysis"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _touch(path: Path) -> None:
    _ensure_dir(path.parent)
    if not path.exists():
        path.touch()


def _write_json(path: Path, payload: dict) -> None:
    _ensure_dir(path.parent)
    if path.exists():
        return
    path.write_text(json.dumps(payload, indent=2))


def seed_demo_data() -> dict:
    email = os.getenv("DEMO_EMAIL", "demo@treehacks.local")
    password = os.getenv("DEMO_PASSWORD", "demo1234")

    user = get_user_by_email(email)
    if not user:
        user = create_user(email, hash_password(password))

    user_id = user["id"]
    if list_videos_for_user(user_id):
        return {"seeded": False, "reason": "videos_exist", "user_id": user_id}

    campaigns = [
        {
            "speed": 1.08,
            "combos": ["hook_caption", "cinematic_grain"],
            "captions": [
                {"id": "hook", "caption": "Cold open: beans hit the grinder."},
                {"id": "benefit", "caption": "Bright aroma, instant wake-up."},
                {"id": "social", "caption": "Barista pour with foam art."},
                {"id": "cta", "caption": "Limited roast drop this week."},
            ],
            "events": [
                {"t_start": 0, "t_end": 3, "caption_id": "hook"},
                {"t_start": 3, "t_end": 7, "caption_id": "benefit"},
                {"t_start": 7, "t_end": 11, "caption_id": "social"},
                {"t_start": 11, "t_end": 15, "caption_id": "cta"},
            ],
        },
        {
            "speed": 1.04,
            "combos": ["vertical_focus", "cutdown_fast"],
            "captions": [
                {"id": "hook", "caption": "Runner hits a sunrise trail."},
                {"id": "product", "caption": "Close-up: TrailMix Pro pack."},
                {"id": "benefit", "caption": "20g protein, zero crash."},
                {"id": "cta", "caption": "Shop the endurance bundle."},
            ],
            "events": [
                {"t_start": 0, "t_end": 4, "caption_id": "hook"},
                {"t_start": 4, "t_end": 7, "caption_id": "product"},
                {"t_start": 7, "t_end": 12, "caption_id": "benefit"},
                {"t_start": 12, "t_end": 16, "caption_id": "cta"},
            ],
        },
        {
            "speed": 1.06,
            "combos": ["focus_backdrop", "hook_caption"],
            "captions": [
                {"id": "hook", "caption": "Before/after skincare glow."},
                {"id": "texture", "caption": "Serum texture on glass."},
                {"id": "routine", "caption": "Night routine in three steps."},
                {"id": "cta", "caption": "Glow kit ships today."},
            ],
            "events": [
                {"t_start": 0, "t_end": 3, "caption_id": "hook"},
                {"t_start": 3, "t_end": 7, "caption_id": "texture"},
                {"t_start": 7, "t_end": 12, "caption_id": "routine"},
                {"t_start": 12, "t_end": 16, "caption_id": "cta"},
            ],
        },
    ]

    for campaign in campaigns:
        video_id = uuid4().hex
        original_filename = f"{video_id}.mp4"
        analysis_filename = f"{video_id}.json"

        original_url = f"/media/original/{original_filename}"
        analysis_url = f"/media/analysis/{analysis_filename}"

        variants = []
        speed_filename = f"{video_id}-speed.mp4"
        variants.append({"name": "speed_up", "url": f"/media/processed/{speed_filename}"})

        for combo in campaign["combos"]:
            combo_filename = f"{video_id}-{combo}.mp4"
            variants.append({"name": combo, "url": f"/media/processed/{combo_filename}"})

        create_video(
            video_id,
            user_id,
            original_url=original_url,
            analysis_url=analysis_url,
            metadata={"speedFactor": campaign["speed"], "combos": campaign["combos"]},
        )

        for variant in variants:
            add_variant(video_id, variant["name"], variant["url"])

        _touch(ORIGINAL_DIR / original_filename)
        for variant in variants:
            _touch(PROCESSED_DIR / Path(variant["url"]).name)

        _write_json(
            ANALYSIS_DIR / analysis_filename,
            {"events": campaign["events"], "captions": campaign["captions"]},
        )

    return {"seeded": True, "user_id": user_id, "count": len(campaigns)}
