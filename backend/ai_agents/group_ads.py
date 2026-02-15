import csv
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - fallback for older runtimes
    ZoneInfo = None

from dotenv import load_dotenv
from openai import OpenAI

from .agent import COLOR_GRADE_STYLES, COMBOS, SPEED_CHANGE_TAGS, _dispatch_tool
from .market_research import run_market_research_agent
from .transform_planner import plan_with_review
from .tool_catalog import BASIC_EDIT_TOOLS

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DEFAULT_GROUP_COUNT = int(os.getenv("AD_GROUP_COUNT", "4") or "4")
# 0 means "auto" (use most available tools).
DEFAULT_MAX_EDITS = int(os.getenv("AD_MAX_EDITS", "0") or "0")
DEFAULT_MIN_VISIBLE = int(os.getenv("AD_MIN_VISIBLE_TRANSFORMS", "2") or "2")
EMBEDDINGS_INPUT_TYPE = os.getenv("EMBEDDINGS_INPUT_TYPE", "CLUSTERING")

STATE_TIMEZONES = {
    "CA": "America/Los_Angeles",
    "WA": "America/Los_Angeles",
    "OR": "America/Los_Angeles",
    "NV": "America/Los_Angeles",
    "AZ": "America/Phoenix",
    "CO": "America/Denver",
    "TX": "America/Chicago",
    "IL": "America/Chicago",
    "MN": "America/Chicago",
    "FL": "America/New_York",
    "NY": "America/New_York",
    "MA": "America/New_York",
    "GA": "America/New_York",
}

CITY_TIMEZONES = {
    "austin": ("US", "America/Chicago"),
    "seattle": ("US", "America/Los_Angeles"),
    "chicago": ("US", "America/Chicago"),
    "new york": ("US", "America/New_York"),
    "miami": ("US", "America/New_York"),
    "san francisco": ("US", "America/Los_Angeles"),
    "los angeles": ("US", "America/Los_Angeles"),
    "boston": ("US", "America/New_York"),
    "denver": ("US", "America/Denver"),
    "dallas": ("US", "America/Chicago"),
    "london": ("UK", "Europe/London"),
    "tokyo": ("JP", "Asia/Tokyo"),
    "berlin": ("DE", "Europe/Berlin"),
    "dublin": ("IE", "Europe/Dublin"),
    "seoul": ("KR", "Asia/Seoul"),
}

ENGLISH_COUNTRIES = {"US", "UK", "IE", "CA", "AU", "NZ", "SG"}

IMPACT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "like",
    "more",
    "most",
    "not",
    "of",
    "on",
    "or",
    "our",
    "out",
    "so",
    "that",
    "the",
    "their",
    "then",
    "these",
    "they",
    "this",
    "to",
    "too",
    "up",
    "was",
    "we",
    "were",
    "with",
    "you",
    "your",
}

IMPACT_KEYWORDS = {
    "new",
    "now",
    "free",
    "limited",
    "only",
    "fast",
    "fresh",
    "power",
    "powerful",
    "save",
    "win",
    "best",
    "easy",
    "instant",
    "today",
    "tonight",
    "exclusive",
    "must",
    "unlock",
    "upgrade",
    "ready",
    "go",
    "glow",
    "boost",
    "strong",
    "bold",
    "pro",
    "ultra",
    "zero",
    "plus",
}


def _in_test_mode() -> bool:
    return os.getenv("AD_TEST_MODE", "0") == "1"


def _load_profiles(csv_path: str) -> list[dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def _has_embedding_env() -> bool:
    return bool(
        os.getenv("ELASTICSEARCH_ENDPOINT")
        and os.getenv("ELASTIC_API_KEY")
        and os.getenv("ELASTIC_INFERENCE_ID")
    )


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


def _cluster_profiles(csv_path: str, group_count: int) -> dict[int, list[dict[str, str]]]:
    rows = _load_profiles(csv_path)
    if not rows:
        return {}

    group_count = max(1, min(group_count, len(rows)))
    vectors: np.ndarray | None = None

    if _has_embedding_env():
        try:
            import cluster_profiles

            texts = [_row_to_text(row) for row in rows]
            embeddings = cluster_profiles._embed_texts(
                texts,
                endpoint=os.getenv("ELASTICSEARCH_ENDPOINT") or "",
                api_key=os.getenv("ELASTIC_API_KEY") or "",
                inference_id=os.getenv("ELASTIC_INFERENCE_ID") or "",
                input_type=EMBEDDINGS_INPUT_TYPE,
            )
            vectors = np.array(embeddings, dtype=np.float32)
        except Exception:
            vectors = None

    if vectors is None:
        vectors = _simple_profile_vectors(rows)

    try:
        import cluster_profiles

        labels, _ = cluster_profiles._kmeans(vectors, group_count)
    except Exception:
        labels = np.array([idx % group_count for idx in range(len(rows))], dtype=np.int64)

    groups: dict[int, list[dict[str, str]]] = {idx: [] for idx in range(group_count)}
    for row, label in zip(rows, labels):
        groups[int(label)].append(row)
    return groups


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
    counts = Counter(terms)
    return [item for item, _ in counts.most_common(limit)]


def _extract_location(demo: str) -> dict[str, str]:
    if not demo:
        return {}
    tokens = [t.strip() for t in demo.split(",") if t.strip()]
    for token in tokens:
        match = re.search(r"([A-Za-z .]+)\\s([A-Z]{2})$", token)
        if not match:
            continue
        city = match.group(1).strip()
        state = match.group(2)
        timezone = STATE_TIMEZONES.get(state)
        return {
            "city": city,
            "state": state,
            "country": "US",
            "timezone": timezone or "",
            "region": f"{city}, {state}",
        }

    lowered = demo.lower()
    for city, (country, tz) in CITY_TIMEZONES.items():
        if city in lowered:
            return {
                "city": city.title(),
                "state": "",
                "country": country,
                "timezone": tz,
                "region": city.title(),
            }

    return {}


def _local_time_bucket(timezone: str | None) -> dict[str, str | int]:
    now = None
    if timezone and ZoneInfo is not None:
        try:
            now = datetime.now(ZoneInfo(timezone))
        except Exception:
            now = None
    if now is None:
        now = datetime.utcnow()
        timezone = "UTC"
    hour = int(now.hour)
    if 5 <= hour < 11:
        bucket = "morning"
    elif 11 <= hour < 17:
        bucket = "afternoon"
    elif 17 <= hour < 21:
        bucket = "evening"
    else:
        bucket = "night"
    return {"timeOfDay": bucket, "localHour": hour, "timezone": timezone}


def _age_bucket(avg_age: int | None) -> str:
    if not avg_age:
        return "unknown"
    if avg_age < 25:
        return "18-24"
    if avg_age < 35:
        return "25-34"
    if avg_age < 45:
        return "35-44"
    return "45+"


def _build_group_context(group_id: int, members: list[dict[str, str]]) -> dict[str, Any]:
    demos = [row.get("demographic_info", "") for row in members if row.get("demographic_info")]
    locations = [_extract_location(demo) for demo in demos]
    regions = [loc.get("region") for loc in locations if loc.get("region")]
    region_counts = Counter(regions)
    region = region_counts.most_common(1)[0][0] if region_counts else ""

    country_counts = Counter([loc.get("country") for loc in locations if loc.get("country")])
    country = country_counts.most_common(1)[0][0] if country_counts else ""

    timezone = ""
    for loc in locations:
        if loc.get("region") == region and loc.get("timezone"):
            timezone = loc.get("timezone") or ""
            break
    time_info = _local_time_bucket(timezone)

    english_speaking = False
    if country:
        english_speaking = country in ENGLISH_COUNTRIES
    elif region:
        english_speaking = True

    is_urban = any("urban" in demo.lower() for demo in demos)
    if not is_urban and region:
        region_lower = region.lower()
        if region_lower in CITY_TIMEZONES:
            is_urban = True

    ages = [age for age in (_parse_age(row.get("age")) for row in members) if age]
    avg_age = round(sum(ages) / len(ages)) if ages else None

    genders = [row.get("gender", "") for row in members if row.get("gender")]
    gender_counts = Counter(genders)
    top_genders = [g for g, _ in gender_counts.most_common(2)]

    search_history = [row.get("previous_search_history", "") for row in members if row.get("previous_search_history")]
    interests = _top_terms(search_history, limit=5)

    return {
        "groupId": group_id,
        "region": region,
        "country": country,
        "timezone": time_info["timezone"],
        "timeOfDay": time_info["timeOfDay"],
        "localHour": time_info["localHour"],
        "englishSpeaking": english_speaking,
        "isUrban": is_urban,
        "avgAge": avg_age,
        "ageBucket": _age_bucket(avg_age),
        "topGenders": top_genders,
        "interests": interests,
    }


def _summarize_group(group_id: int, members: list[dict[str, str]]) -> dict[str, Any]:
    context = _build_group_context(group_id, members)
    avg_age = context.get("avgAge")
    top_genders = ", ".join(context.get("topGenders") or [])

    demographic_samples = [row.get("demographic_info", "") for row in members if row.get("demographic_info")]
    demo_preview = "; ".join(demographic_samples[:2]) if demographic_samples else ""

    interests_text = ", ".join(context.get("interests") or [])

    parts = [f"Group {group_id}"]
    if avg_age:
        parts.append(f"avg age {avg_age}")
    if top_genders:
        parts.append(f"top genders: {top_genders}")
    if demo_preview:
        parts.append(f"demo: {demo_preview}")
    if interests_text:
        parts.append(f"interests: {interests_text}")

    description = ". ".join(parts)
    return {
        "id": group_id,
        "label": f"Group {group_id}",
        "description": description,
        "member_count": len(members),
        "context": context,
    }


def build_groups(csv_path: str, group_count: int | None = None) -> list[dict[str, Any]]:
    count = max(1, group_count or DEFAULT_GROUP_COUNT)
    groups = _cluster_profiles(csv_path, count)
    summaries = []
    for group_id, members in sorted(groups.items()):
        summaries.append(_summarize_group(group_id, members))
    return summaries


def _compact_lines(items: list[dict], key: str, limit: int = 8) -> list[str]:
    lines = []
    for item in items[:limit]:
        value = item.get(key)
        if not value:
            continue
        text = str(value).strip()
        if text:
            lines.append(text)
    return lines


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1).replace("```", "", 1)
    return cleaned.strip()


def _truncate(text: str, limit: int = 1400) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[:limit].rsplit(" ", 1)[0]
    return (trimmed or cleaned[:limit]).rstrip() + "..."


def _clip_text(text: str, limit: int = 32) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[:limit].rsplit(" ", 1)[0]
    return (trimmed or cleaned[:limit]).rstrip()


def _extract_hook(text: str, limit: int = 32) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    candidates = [c.strip(" \"'") for c in re.split(r"[.!?]+", cleaned) if c.strip()]
    for candidate in candidates:
        words = candidate.split()
        if 3 <= len(words) <= 10:
            return _clip_text(candidate, limit=limit)
    if candidates:
        return _clip_text(candidates[0], limit=limit)
    return _clip_text(cleaned, limit=limit)


def _extract_json(text: str) -> dict:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        return {}
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            return {}
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def _run_group_research(audience_description: str, context: dict | None = None) -> dict:
    if _in_test_mode():
        return {
            "ok": True,
            "audience": audience_description,
            "insights": "Test mode: no research run.",
            "citations": [],
            "model": "test",
            "transformations": [],
        }
    region = None
    extra_focus: list[str] = []
    if context:
        region = context.get("region") or context.get("country")
        if context.get("timeOfDay"):
            extra_focus.append(f"Time-of-day preferences ({context['timeOfDay']})")
        if context.get("isUrban"):
            extra_focus.append("Urban/city creative preferences")
        if context.get("englishSpeaking") is False:
            extra_focus.append("Non-English market messaging")

    result = run_market_research_agent(
        audience_description=audience_description,
        region=region,
        extra_focus=extra_focus,
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error", "Market research failed"),
            "audience": audience_description,
        }
    return {
        "ok": True,
        "audience": result.get("audience") or audience_description,
        "insights": result.get("insights", ""),
        "citations": result.get("citations", []),
        "model": result.get("model"),
        "transformations": result.get("transformations", []),
    }


PLANNER_TOOLS = [
    "change_speed_video",
    "color_grade_video",
    "apply_combo",
    "add_text_overlay_video",
    "blur_backdrop_video",
    "reframe_vertical_video",
    "add_film_grain_video",
    "trim_video",
    "replace_text_region_video",
]

PLANNER_ORDER = [
    "trim_video",
    "change_speed_video",
    "color_grade_video",
    "blur_backdrop_video",
    "reframe_vertical_video",
    "add_film_grain_video",
    "add_text_overlay_video",
    "replace_text_region_video",
    "apply_combo",
]

COMBO_FEATURES = {
    "vertical_focus": {"reframe_vertical_video", "color_grade_video"},
    "hook_caption": {"trim_video", "add_text_overlay_video"},
    "cutdown_fast": {"trim_video", "change_speed_video"},
    "focus_backdrop": {"blur_backdrop_video", "color_grade_video"},
    "cinematic_grain": {"color_grade_video", "add_film_grain_video"},
}

VISIBLE_TOOLS = {
    "color_grade_video",
    "apply_combo",
    "add_text_overlay_video",
    "blur_backdrop_video",
    "reframe_vertical_video",
    "add_film_grain_video",
    "trim_video",
    "replace_text_region_video",
}


def _recommended_speed_tag(context: dict[str, Any]) -> str:
    if not context:
        return "neutral"
    if context.get("englishSpeaking") is False:
        return "slow_2"
    tod = context.get("timeOfDay")
    if tod == "morning":
        return "fast_2"
    if tod in {"evening", "night"}:
        return "slow_2"
    if tod == "afternoon":
        return "fast_2"
    return "fast_2"


def _recommended_grade_style(context: dict[str, Any]) -> str:
    if not context:
        return "neutral_clean"
    tod = context.get("timeOfDay")
    if tod == "night":
        return "moody_dark"
    if tod == "morning":
        return "bright_airy"
    if context.get("isUrban"):
        return "cool_urban"
    if context.get("ageBucket") in {"18-24", "25-34"}:
        return "vibrant_pop"
    return "warm_glow"


def _recommended_combo(context: dict[str, Any]) -> str:
    if not context:
        return "vertical_focus"
    tod = context.get("timeOfDay")
    if tod == "morning":
        return "cutdown_fast"
    if tod in {"evening", "night"}:
        return "cinematic_grain"
    if context.get("isUrban"):
        return "focus_backdrop"
    if context.get("ageBucket") in {"18-24", "25-34"}:
        return "hook_caption"
    return "vertical_focus"


def _pick_overlay_text(research: dict | None, analysis: dict | None) -> str:
    if analysis:
        audio_segments = analysis.get("audio_segments") or []
        for segment in audio_segments:
            hook = _extract_hook(str(segment.get("text") or ""), limit=32)
            if hook:
                return hook
    if research:
        insights = str(research.get("insights") or "").strip()
        if insights:
            snippet = insights.split(".")[0].strip()
            if snippet:
                return _clip_text(snippet, limit=32)
    if analysis:
        captions = analysis.get("captions") or []
        if captions:
            text = str(captions[0].get("caption") or "").strip()
            if text:
                return _clip_text(text, limit=32)
    return "Made for you"


def _stable_roll(*parts: Any) -> float:
    seed = "::".join([str(p) for p in parts if p not in (None, "")])
    if not seed:
        seed = "0"
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / float(0xFFFFFFFF)


def _overlay_target_share(context: dict[str, Any], analysis: dict | None) -> float:
    target = 0.33
    if context.get("englishSpeaking") is False:
        target += 0.08
    if context.get("ageBucket") == "45+":
        target += 0.08
    if analysis:
        if analysis.get("audio_segments"):
            target += 0.05
        if not analysis.get("audio_segments") and not analysis.get("captions"):
            target -= 0.15
    else:
        target -= 0.1
    return min(max(target, 0.2), 0.55)


def _overlay_guidance(
    video_id: str | None,
    group_id: int,
    context: dict[str, Any],
    analysis: dict | None,
    override: bool | None = None,
) -> dict[str, Any]:
    target = _overlay_target_share(context, analysis)
    roll = _stable_roll(video_id or "", group_id, context.get("region"), context.get("timeOfDay"))
    should_apply = roll < target
    reason = "Apply overlays for roughly a third of variants while adapting to audience and content."
    if override is not None:
        should_apply = bool(override)
        reason = "Batch selection targets ~33% of variants in this group set."
    return {
        "target_share": round(target, 3),
        "roll": round(roll, 3),
        "should_apply": should_apply,
        "reason": reason,
    }


def _overlay_font_size(context: dict[str, Any]) -> int:
    if context.get("ageBucket") == "45+":
        return 42
    if context.get("ageBucket") in {"18-24", "25-34"}:
        return 36
    return 38


def _impact_phrase(text: str, context: dict[str, Any]) -> str:
    if not text:
        return ""
    hook = _extract_hook(text, limit=64)
    words = re.findall(r"[A-Za-z0-9']+", hook)
    if not words:
        return _clip_text(hook, limit=32)

    filtered = [w for w in words if w.lower() not in IMPACT_STOPWORDS]
    phrase_words = filtered[:4] if len(filtered) >= 2 else words[:4]
    phrase = " ".join(phrase_words)
    phrase = _clip_text(phrase, limit=32)

    if context.get("englishSpeaking") is False:
        return phrase
    if len(phrase.split()) <= 4:
        return phrase.upper()
    return phrase


def _impact_score(text: str, start: float, end: float, duration: float | None, source: str) -> float:
    if not text:
        return 0.0
    lower = text.lower()
    score = 0.2
    if "!" in text:
        score += 0.3
    for keyword in IMPACT_KEYWORDS:
        if keyword in lower:
            score += 0.6
    words = re.findall(r"[A-Za-z0-9']+", text)
    if 2 <= len(words) <= 6:
        score += 0.5
    if len(words) > 12:
        score -= 0.3
    if source == "audio":
        score += 0.2
    if duration and duration > 0:
        mid = (start + end) / 2.0
        ratio = mid / duration
        if ratio < 0.08 or ratio > 0.92:
            score -= 0.25
        elif 0.2 <= ratio <= 0.75:
            score += 0.2
    return score


def _normalize_overlay_window(start: float, end: float, duration: float | None) -> tuple[float, float]:
    safe_start = max(0.0, float(start))
    safe_end = max(safe_start, float(end))
    length = safe_end - safe_start
    target = 1.6 if length < 1.0 else min(length, 2.6)
    if length > target:
        safe_start = safe_start + (length - target) / 2.0
    safe_end = safe_start + target
    if duration and duration > 0:
        safe_end = min(safe_end, duration)
    return round(safe_start, 3), round(safe_end, 3)


def _overlay_candidates(analysis: dict | None, context: dict[str, Any]) -> list[dict[str, Any]]:
    if not analysis:
        return []
    duration = analysis.get("duration")
    duration_value = float(duration) if isinstance(duration, (int, float)) else None
    candidates: list[dict[str, Any]] = []

    audio_segments = analysis.get("audio_segments") or []
    for segment in audio_segments[:12]:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        phrase = _impact_phrase(text, context)
        if not phrase:
            continue
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start + 1.5))
        start, end = _normalize_overlay_window(start, end, duration_value)
        score = _impact_score(text, start, end, duration_value, "audio")
        candidates.append(
            {"text": phrase, "start": start, "end": end, "source": "audio", "score": score}
        )

    captions = analysis.get("captions") or []
    caption_map = {c.get("id"): c for c in captions if isinstance(c, dict)}
    events = analysis.get("events") or []
    for event in events[:20]:
        caption = caption_map.get(event.get("caption_id"))
        if not caption:
            continue
        text = str(caption.get("caption") or "").strip()
        if not text:
            continue
        phrase = _impact_phrase(text, context)
        if not phrase:
            continue
        start = float(event.get("t_start", 0.0))
        end = float(event.get("t_end", start + 1.8))
        start, end = _normalize_overlay_window(start, end, duration_value)
        score = _impact_score(text, start, end, duration_value, "visual")
        candidates.append(
            {"text": phrase, "start": start, "end": end, "source": "visual", "score": score}
        )

    scene_captions = analysis.get("scene_captions") or []
    for item in scene_captions[:10]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("caption") or "").strip()
        if not text:
            continue
        phrase = _impact_phrase(text, context)
        if not phrase:
            continue
        start = float(item.get("t", 0.0))
        end = start + 2.0
        start, end = _normalize_overlay_window(start, end, duration_value)
        score = _impact_score(text, start, end, duration_value, "scene")
        candidates.append(
            {"text": phrase, "start": start, "end": end, "source": "scene", "score": score}
        )

    return candidates


def _select_overlay_moment(analysis: dict | None, context: dict[str, Any]) -> dict[str, Any]:
    candidates = _overlay_candidates(analysis, context)
    if not candidates:
        return {}
    candidates.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return candidates[0]


def _impact_moments_for_prompt(analysis: dict | None, context: dict[str, Any], limit: int = 4) -> list[dict[str, Any]]:
    candidates = _overlay_candidates(analysis, context)
    if not candidates:
        return []
    candidates.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    moments: list[dict[str, Any]] = []
    for item in candidates[:limit]:
        moments.append(
            {
                "start": item.get("start"),
                "end": item.get("end"),
                "text": item.get("text"),
                "source": item.get("source"),
            }
        )
    return moments


def _apply_overlay_guidance(
    decisions: list[dict[str, Any]],
    overlay_guidance: dict[str, Any],
    max_transforms: int | None,
) -> None:
    if not overlay_guidance or not overlay_guidance.get("should_apply"):
        return
    overlay = next((d for d in decisions if d.get("tool") == "add_text_overlay_video"), None)
    if not overlay or overlay.get("apply"):
        return
    applied = sum(1 for d in decisions if d.get("apply"))
    if isinstance(max_transforms, int) and max_transforms > 0 and applied >= max_transforms:
        return
    overlay["apply"] = True
    overlay["forced"] = True
    overlay["reason"] = (overlay.get("reason") or "").strip()
    suffix = " Overlay guidance requested an impact text moment."
    overlay["reason"] = (overlay["reason"] + suffix).strip()


def _rank_overlay_groups(video_id: str | None, groups: list[dict[str, Any]]) -> list[int]:
    scored: list[tuple[float, int]] = []
    for group in groups:
        group_id = int(group.get("id", 0))
        roll = _stable_roll(video_id or "", group_id, group.get("label"), group.get("description"))
        scored.append((roll, group_id))
    scored.sort(key=lambda item: item[0])
    return [group_id for _, group_id in scored]


def _select_overlay_group_ids(
    video_id: str | None,
    groups: list[dict[str, Any]],
    target_ratio: float = 0.33,
) -> set[int]:
    if not groups:
        return set()
    ranked = _rank_overlay_groups(video_id, groups)
    target = max(1, int(round(len(ranked) * target_ratio)))
    return set(ranked[:target])


def _plan_overlay_group_ids(
    video_id: str | None,
    groups: list[dict[str, Any]],
    analysis: dict,
    target_ratio: float = 0.33,
) -> set[int]:
    if not groups:
        return set()
    target_count = max(1, int(round(len(groups) * target_ratio)))

    if _in_test_mode() or not os.getenv("OPENAI_API_KEY"):
        ranked = _rank_overlay_groups(video_id, groups)
        return set(ranked[:target_count])

    captions = analysis.get("captions", []) if isinstance(analysis, dict) else []
    caption_lines = _compact_lines(captions, "caption", limit=12)
    audio_segments = analysis.get("audio_segments", []) if isinstance(analysis, dict) else []
    audio_lines: list[str] = []
    for segment in audio_segments[:12]:
        hook = _extract_hook(str(segment.get("text") or ""), limit=120)
        if hook:
            audio_lines.append(hook)

    group_payload = []
    for group in groups:
        group_payload.append(
            {
                "id": group.get("id"),
                "label": group.get("label"),
                "description": group.get("description"),
                "context": group.get("context"),
            }
        )

    system_prompt = (
        "You are a creative planning agent. Choose which audience groups should receive on-screen text overlays. "
        "Pick the groups where short impact captions would add clarity or punch (e.g., non-English, older, "
        "dense messaging, strong hook moments). Return JSON only."
    )
    user_payload = {
        "target_count": target_count,
        "target_ratio": target_ratio,
        "groups": group_payload,
        "transcript_excerpts": audio_lines,
        "caption_highlights": caption_lines,
        "instructions": (
            "Return JSON with keys: ranked_group_ids (ordered list of group ids from most to least suited). "
            "Use each group id at most once."
        ),
    }

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            temperature=0.2,
        )
    except Exception:
        ranked = _rank_overlay_groups(video_id, groups)
        return set(ranked[:target_count])

    raw = response.choices[0].message.content or ""
    payload = _extract_json(raw)
    ranked_ids = payload.get("ranked_group_ids") if isinstance(payload, dict) else None
    if not isinstance(ranked_ids, list):
        ranked = _rank_overlay_groups(video_id, groups)
        return set(ranked[:target_count])

    group_ids = {int(group.get("id", 0)) for group in groups}
    ordered: list[int] = []
    seen: set[int] = set()
    for item in ranked_ids:
        try:
            gid = int(item)
        except (TypeError, ValueError):
            continue
        if gid not in group_ids or gid in seen:
            continue
        ordered.append(gid)
        seen.add(gid)

    if not ordered:
        ranked = _rank_overlay_groups(video_id, groups)
        return set(ranked[:target_count])

    if len(ordered) < target_count:
        ranked = _rank_overlay_groups(video_id, groups)
        for gid in ranked:
            if gid in seen:
                continue
            ordered.append(gid)
            if len(ordered) >= target_count:
                break
    else:
        ordered = ordered[:target_count]

    return set(ordered)


def _ensure_visible_decisions(decisions: list[dict[str, Any]], context: dict[str, Any]) -> None:
    visible_tools = {
        "color_grade_video",
        "apply_combo",
        "add_text_overlay_video",
        "blur_backdrop_video",
        "reframe_vertical_video",
        "add_film_grain_video",
        "trim_video",
        "replace_text_region_video",
    }
    if any(d.get("apply") for d in decisions if d.get("tool") in visible_tools):
        return
    decisions.append(
        {
            "tool": "color_grade_video",
            "apply": True,
            "reason": "Ensure a visible change even if other edits are subtle.",
            "summary": "grade " + _recommended_grade_style(context),
            "args": {
                "gradeStyle": _recommended_grade_style(context),
                "gradeNote": "Guarantee a visible look shift.",
            },
        }
    )


def _heuristic_decisions(
    context: dict[str, Any],
    analysis: dict,
    group_id: int,
    video_id: str | None = None,
    overlay_override: bool | None = None,
) -> list[dict[str, Any]]:
    speed_tag = _recommended_speed_tag(context)
    grade_style = _recommended_grade_style(context)
    combo_name = _recommended_combo(context)
    overlay_guidance = _overlay_guidance(video_id, group_id, context, analysis, override=overlay_override)
    overlay_moment = _select_overlay_moment(analysis, context)
    overlay_text = overlay_moment.get("text") or _pick_overlay_text(None, analysis)
    overlay_start = overlay_moment.get("start", 0.6)
    overlay_end = overlay_moment.get("end", 2.4)
    overlay_font = _overlay_font_size(context)

    decisions = [
        {
            "tool": "change_speed_video",
            "apply": speed_tag != "neutral",
            "reason": "Time-of-day or language pacing heuristic.",
            "summary": f"speed {speed_tag}",
            "args": {"changeTag": speed_tag, "changeNote": "Heuristic pace adjustment."},
            "source": "heuristic",
        },
        {
            "tool": "color_grade_video",
            "apply": True,
            "reason": "Heuristic tone shift for audience/context.",
            "summary": f"grade {grade_style}",
            "args": {"gradeStyle": grade_style, "gradeNote": "Heuristic grade."},
            "source": "heuristic",
        },
        {
            "tool": "apply_combo",
            "apply": group_id % 2 == 0,
            "reason": "Alternate combos to keep group variants distinct.",
            "summary": f"combo {combo_name}",
            "args": {"comboName": combo_name},
            "source": "heuristic",
        },
        {
            "tool": "add_text_overlay_video",
            "apply": bool(overlay_guidance.get("should_apply")),
            "reason": "Overlay guidance favors impact text for about half of variants.",
            "summary": "overlay text",
            "args": {
                "text": overlay_text,
                "x": 32,
                "y": 32,
                "fontSize": overlay_font,
                "start": overlay_start,
                "end": overlay_end,
            },
            "source": "heuristic",
        },
        {
            "tool": "blur_backdrop_video",
            "apply": False,
            "reason": "Not required by heuristics.",
            "summary": "skip blur",
            "args": {},
            "source": "heuristic",
        },
        {
            "tool": "reframe_vertical_video",
            "apply": False,
            "reason": "Not required by heuristics.",
            "summary": "skip reframe",
            "args": {},
            "source": "heuristic",
        },
        {
            "tool": "add_film_grain_video",
            "apply": False,
            "reason": "Not required by heuristics.",
            "summary": "skip grain",
            "args": {},
            "source": "heuristic",
        },
        {
            "tool": "trim_video",
            "apply": False,
            "reason": "Not required by heuristics.",
            "summary": "skip trim",
            "args": {},
            "source": "heuristic",
        },
        {
            "tool": "replace_text_region_video",
            "apply": False,
            "reason": "Requires explicit region coordinates.",
            "summary": "skip replace text",
            "args": {},
            "source": "heuristic",
        },
    ]
    _ensure_visible_decisions(decisions, context)
    return decisions




def plan_group_transformations(
    audience_description: str,
    analysis: dict,
    research: dict | None,
    context: dict[str, Any],
    video_id: str | None = None,
    overlay_override: bool | None = None,
    max_edits: int | None = None,
) -> dict[str, Any]:
    if _in_test_mode():
        raise RuntimeError("AD_TEST_MODE=1 disables OpenAI planning. Unset AD_TEST_MODE to use OpenAI-only decisions.")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI-only planning.")

    tool_count = len(PLANNER_TOOLS)
    if max_edits is not None:
        edits = max_edits
    elif DEFAULT_MAX_EDITS > 0:
        edits = DEFAULT_MAX_EDITS
    else:
        edits = max(1, tool_count - 1)
    edits = max(1, min(int(edits), tool_count))
    audio_segments = analysis.get("audio_segments", []) if isinstance(analysis, dict) else []
    captions = analysis.get("captions", []) if isinstance(analysis, dict) else []
    caption_lines = _compact_lines(captions, "caption", limit=10)
    audio_lines: list[str] = []
    for segment in audio_segments[:10]:
        hook = _extract_hook(str(segment.get("text") or ""), limit=120)
        if hook:
            audio_lines.append(hook)

    research_summary = _truncate(research.get("insights", "")) if research else ""
    research_citations = research.get("citations", []) if research else []
    overlay_guidance = _overlay_guidance(
        video_id,
        context.get("groupId", 0),
        context,
        analysis,
        override=overlay_override,
    )
    impact_moments = _impact_moments_for_prompt(analysis, context, limit=4)

    user_payload = {
        "audience": audience_description,
        "group_context": context,
        "research_summary": research_summary,
        "research_citations": research_citations,
        "transcript_excerpts": audio_lines,
        "caption_highlights": caption_lines,
        "impact_moments": impact_moments,
        "overlay_guidance": overlay_guidance,
        "available_tools": PLANNER_TOOLS,
        "combo_names": COMBOS,
        "speed_tags": SPEED_CHANGE_TAGS,
        "grade_styles": COLOR_GRADE_STYLES,
        "max_transformations": edits,
        "target_transformations": edits,
        "min_visible_transforms": DEFAULT_MIN_VISIBLE,
        "required_output": {
            "decisions": [
                {
                    "tool": "change_speed_video",
                    "apply": True,
                    "reason": "Why this tool is or isn't applied.",
                    "summary": "short summary",
                    "args": {"changeTag": "fast_2", "changeNote": "note"},
                }
            ]
        },
    }

    try:
        plan = plan_with_review(
            payload=user_payload,
            tools=PLANNER_TOOLS,
            visible_tools=VISIBLE_TOOLS,
            min_visible=DEFAULT_MIN_VISIBLE,
            context=context,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "decisions": _heuristic_decisions(
                context,
                analysis,
                context.get("groupId", 0),
                video_id=video_id,
                overlay_override=overlay_override,
            ),
        }

    decisions = plan.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return {
            "ok": False,
            "error": plan.get("error", "Planner returned no decisions"),
            "decisions": _heuristic_decisions(
                context,
                analysis,
                context.get("groupId", 0),
                video_id=video_id,
                overlay_override=overlay_override,
            ),
        }

    cleaned: list[dict[str, Any]] = []
    for item in decisions:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "").strip()
        if tool not in PLANNER_TOOLS:
            continue
        cleaned.append(
            {
                "tool": tool,
                "apply": bool(item.get("apply")),
                "reason": str(item.get("reason") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "args": item.get("args") if isinstance(item.get("args"), dict) else {},
                "forced": bool(item.get("forced", False)),
                "source": "ai",
            }
        )

    _apply_overlay_guidance(cleaned, overlay_guidance, edits)

    return {
        "ok": plan.get("ok", True),
        "model": plan.get("model", MODEL),
        "raw": plan.get("raw"),
        "error": plan.get("error"),
        "decisions": cleaned,
    }


def _fill_tool_args(
    tool: str,
    args: dict[str, Any],
    context: dict[str, Any],
    analysis: dict | None,
    research: dict | None,
) -> dict[str, Any]:
    payload = dict(args or {})
    if tool == "change_speed_video":
        payload.setdefault("changeTag", _recommended_speed_tag(context))
        payload.setdefault(
            "changeNote",
            f"Pacing tuned for {context.get('timeOfDay', 'day')} and language.",
        )
    elif tool == "color_grade_video":
        payload.setdefault("gradeStyle", _recommended_grade_style(context))
        payload.setdefault(
            "gradeNote",
            f"Tone matched to {context.get('timeOfDay', 'day')} / urban={context.get('isUrban')}.",
        )
    elif tool == "apply_combo":
        combo = payload.setdefault("comboName", _recommended_combo(context))
        if combo == "hook_caption":
            overlay_moment = _select_overlay_moment(analysis, context)
            payload.setdefault("text", overlay_moment.get("text") or _pick_overlay_text(research, analysis))
            payload.setdefault("x", 32)
            payload.setdefault("y", 32)
            payload.setdefault("fontSize", _overlay_font_size(context))
            payload.setdefault("start", overlay_moment.get("start", 0.6))
            payload.setdefault("end", overlay_moment.get("end", 2.4))
    elif tool == "add_text_overlay_video":
        overlay_moment = _select_overlay_moment(analysis, context)
        payload.setdefault("text", overlay_moment.get("text") or _pick_overlay_text(research, analysis))
        payload.setdefault("x", 32)
        payload.setdefault("y", 32)
        payload.setdefault("fontSize", _overlay_font_size(context))
        payload.setdefault("start", overlay_moment.get("start", 0.6))
        payload.setdefault("end", overlay_moment.get("end", 2.4))
    elif tool == "blur_backdrop_video":
        payload.setdefault("scale", 0.84)
        payload.setdefault("blur", 22.0)
    elif tool == "reframe_vertical_video":
        payload.setdefault("width", 1080)
        payload.setdefault("height", 1920)
        payload.setdefault("blur", 28.0)
    elif tool == "add_film_grain_video":
        payload.setdefault("strength", 14.0)
    elif tool == "trim_video":
        payload.setdefault("start", 0.0)
        payload.setdefault("duration", 8.0)
    elif tool == "replace_text_region_video":
        payload.setdefault("x", 32)
        payload.setdefault("y", 32)
        payload.setdefault("w", 480)
        payload.setdefault("h", 120)
        overlay_moment = _select_overlay_moment(analysis, context)
        payload.setdefault("text", overlay_moment.get("text") or _pick_overlay_text(research, analysis))
        payload.setdefault("fontSize", 32)
        payload.setdefault("color", "white")
        payload.setdefault("boxColor", "black@0.6")
    return payload


def _resolve_combo_conflicts(decisions: list[dict[str, Any]]) -> None:
    # We keep all tools applied; annotate conflicts without disabling anything.
    combo = None
    for decision in decisions:
        if decision.get("tool") == "apply_combo" and decision.get("apply"):
            combo = decision.get("args", {}).get("comboName")
            break
    if not combo:
        return
    conflicts = COMBO_FEATURES.get(combo, set())
    if not conflicts:
        return
    for decision in decisions:
        tool = decision.get("tool")
        if tool in conflicts and decision.get("apply"):
            decision["reason"] = (decision.get("reason") or "") + " Overlaps combo; keeping both applied."


def _ensure_min_visible(decisions: list[dict[str, Any]], min_visible: int) -> None:
    visible_tools = [
        "color_grade_video",
        "add_text_overlay_video",
        "add_film_grain_video",
        "blur_backdrop_video",
        "reframe_vertical_video",
        "trim_video",
    ]
    applied_visible = sum(
        1 for d in decisions if d.get("apply") and d.get("tool") in visible_tools
    )
    if applied_visible >= min_visible:
        return

    for tool in visible_tools:
        if applied_visible >= min_visible:
            break
        for decision in decisions:
            if decision.get("tool") != tool:
                continue
            if decision.get("apply"):
                break
            decision["apply"] = True
            decision["forced"] = True
            decision["reason"] = (decision.get("reason") or "") + " Forced to meet minimum visible transforms."
            applied_visible += 1
            break


def _apply_decisions(
    video_id: str,
    group_id: int,
    original_path: Path,
    decisions: list[dict[str, Any]],
    processed_dir: Path,
    context: dict[str, Any],
    analysis: dict | None,
    research: dict | None,
    enforce_min_visible: bool = True,
) -> tuple[str | None, list[dict[str, Any]]]:
    ordered = {tool: idx for idx, tool in enumerate(PLANNER_ORDER)}
    decisions.sort(key=lambda item: ordered.get(item.get("tool"), 999))

    for decision in decisions:
        if "applied" not in decision:
            decision["applied"] = False

    for decision in decisions:
        if decision.get("tool") == "apply_combo" and decision.get("apply"):
            decision["args"] = _fill_tool_args(
                "apply_combo", decision.get("args") or {}, context, analysis, research
            )

    _resolve_combo_conflicts(decisions)
    if enforce_min_visible:
        _ensure_min_visible(decisions, DEFAULT_MIN_VISIBLE)

    current_input = str(original_path)
    applied_steps = 0
    for decision in decisions:
        if not decision.get("apply"):
            continue
        tool = decision.get("tool")
        if not tool:
            continue

        args = decision.get("args") or {}
        args = _fill_tool_args(tool, args, context, analysis, research)

        if tool == "replace_text_region_video":
            required = {"x", "y", "w", "h", "text"}
            if not required.issubset(args.keys()):
                decision["apply"] = False
                decision["reason"] = (decision.get("reason") or "") + " Missing region args; skipped."
                continue

        applied_steps += 1
        step_output = processed_dir / f"{video_id}-group{group_id}-step{applied_steps}.mp4"
        try:
            result = _dispatch_tool(tool, args, current_input, str(step_output))
            decision["applied"] = True
            decision["outputPath"] = result.get("outputPath")
            current_input = str(step_output)
        except Exception as exc:
            decision["applied"] = False
            decision["error"] = str(exc)

    if applied_steps == 0:
        return None, decisions

    return current_input, decisions


def _run_edit_agent(request: str, input_path: str, output_path: str) -> dict:
    if _in_test_mode():
        args = {"changeTag": "fast_2", "changeNote": "Test mode fallback."}
        args["inputPath"] = input_path
        args["outputPath"] = output_path
        try:
            result = _dispatch_tool("speed_up_video", args, input_path, output_path)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "tool": "speed_up_video", "args": args}
        return {"ok": True, "tool": "speed_up_video", "args": args, "outputPath": result.get("outputPath")}

    system_prompt = (
        "You are a video editing agent. Choose the single best tool to execute the request. "
        "Always call exactly one tool."
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Request: {request}\n"
                    f"inputPath: {input_path}\n"
                    f"outputPath: {output_path}\n"
                    "Use only the available tools."
                ),
            },
        ],
        tools=BASIC_EDIT_TOOLS,
        tool_choice="required",
    )

    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    if not tool_calls:
        return {"ok": False, "error": "No tool calls"}

    call = tool_calls[0]
    args = {}
    if call.function and call.function.arguments:
        try:
            args = json.loads(call.function.arguments)
        except json.JSONDecodeError:
            args = {}

    name = call.function.name if call.function else ""
    args["inputPath"] = input_path
    args["outputPath"] = output_path

    try:
        result = _dispatch_tool(name, args, input_path, output_path)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tool": name, "args": args}

    return {"ok": True, "tool": name, "args": args, "outputPath": result.get("outputPath")}


def _summary_from_tool(tool_name: str, args: dict) -> str:
    if tool_name in {"speed_up_video", "change_speed_video"}:
        tag = args.get("changeTag") or "neutral"
        return f"speed {tag}"
    if tool_name == "color_grade_video":
        style = args.get("gradeStyle") or "neutral_clean"
        return f"grade {style}"
    if tool_name == "apply_combo":
        combo = args.get("comboName") or "combo"
        return f"combo {combo}"
    if tool_name == "add_text_overlay_video":
        text = str(args.get("text") or "caption").strip()
        return f"overlay '{text[:24]}'"
    if tool_name == "replace_text_region_video":
        text = str(args.get("text") or "replace text").strip()
        return f"replace text '{text[:24]}'"
    if tool_name == "blur_backdrop_video":
        return "blur backdrop"
    if tool_name == "reframe_vertical_video":
        return "reframe vertical"
    if tool_name == "add_film_grain_video":
        return "add film grain"
    if tool_name == "trim_video":
        return "trim segment"
    return tool_name


def _condense_summary(parts: list[str]) -> str:
    summary = "; ".join([p for p in parts if p])
    if len(summary) <= 140:
        return summary
    return summary[:137].rstrip() + "..."


def _shorten_summary(text: str, limit: int = 80) -> str:
    cleaned = (text or "").strip()
    if cleaned.endswith("."):
        cleaned = cleaned[:-1]
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def generate_group_variants(
    video_id: str,
    original_path: Path,
    analysis: dict,
    processed_dir: Path,
    csv_path: str,
    group_count: int | None = None,
    max_edits: int | None = None,
) -> tuple[list[dict], list[dict]]:
    groups = build_groups(csv_path, group_count)
    variants: list[dict] = []
    metadata_updates: list[dict] = []

    if not groups:
        return variants, metadata_updates

    overlay_group_ids = _plan_overlay_group_ids(video_id, groups, analysis, target_ratio=0.33)

    for group in groups:
        group_id = group["id"]
        context = group.get("context") or {}
        overlay_override = group_id in overlay_group_ids
        research = _run_group_research(group["description"], context=context)
        plan = plan_group_transformations(
            group["description"],
            analysis,
            research=research,
            context=context,
            video_id=video_id,
            overlay_override=overlay_override,
            max_edits=max_edits,
        )
        decisions = plan.get("decisions") or []
        for decision in decisions:
            if not decision.get("summary"):
                decision["summary"] = _summary_from_tool(decision.get("tool", ""), decision.get("args") or {})
            decision["summary"] = _shorten_summary(decision.get("summary") or "")

        final_path, decisions = _apply_decisions(
            video_id=video_id,
            group_id=group_id,
            original_path=original_path,
            decisions=decisions,
            processed_dir=processed_dir,
            context=context,
            analysis=analysis,
            research=research,
            enforce_min_visible=not plan.get("ok", True),
        )

        if not final_path:
            continue

        final_output = processed_dir / f"{video_id}-group{group_id}.mp4"
        if Path(final_path) != final_output:
            Path(final_path).replace(final_output)

        variant_name = f"group-{group_id}"
        variants.append({"name": variant_name, "url": f"/media/processed/{final_output.name}"})

        metadata_updates.append(
            {
                "groupId": group_id,
                "label": group.get("label"),
                "summary": _condense_summary([d.get("summary") for d in decisions if d.get("apply")]),
                "changes": decisions,
                "research": research,
                "context": context,
                "planner": {
                    "ok": plan.get("ok", True),
                    "error": plan.get("error"),
                    "model": plan.get("model"),
                    "raw": _truncate(plan.get("raw", ""), limit=2000),
                },
                "variantName": variant_name,
                "variantUrl": f"/media/processed/{final_output.name}",
            }
        )

    return variants, metadata_updates
