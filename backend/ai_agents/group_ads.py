import csv
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

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
DEFAULT_MAX_EDITS = int(os.getenv("AD_MAX_EDITS", "3") or "3")
DEFAULT_MIN_VISIBLE = int(os.getenv("AD_MIN_VISIBLE_TRANSFORMS", "2") or "2")

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


def _cluster_profiles(csv_path: str, group_count: int) -> dict[int, list[dict[str, str]]]:
    try:
        if _has_embedding_env():
            import cluster_profiles

            clustered = cluster_profiles.cluster(n_clusters=group_count, csv_path=csv_path)
            groups: dict[int, list[dict[str, str]]] = {}
            for row in clustered:
                group_id = int(row.get("cluster", 0))
                groups.setdefault(group_id, []).append(row)
            if groups:
                return groups
    except Exception:
        pass

    rows = _load_profiles(csv_path)
    groups = {idx: [] for idx in range(group_count)}
    for idx, row in enumerate(rows):
        group_id = idx % group_count
        groups[group_id].append(row)
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
    if research:
        insights = str(research.get("insights") or "").strip()
        if insights:
            snippet = insights.split(".")[0].strip()
            if snippet:
                return snippet[:32]
    if analysis:
        captions = analysis.get("captions") or []
        if captions:
            text = str(captions[0].get("caption") or "").strip()
            if text:
                return text[:32]
    return "Made for you"


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


def _heuristic_decisions(context: dict[str, Any], analysis: dict, group_id: int) -> list[dict[str, Any]]:
    speed_tag = _recommended_speed_tag(context)
    grade_style = _recommended_grade_style(context)
    combo_name = _recommended_combo(context)
    overlay_text = _pick_overlay_text(None, analysis)

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
            "apply": group_id % 2 == 1,
            "reason": "Add light contextual copy for distinctiveness.",
            "summary": "overlay text",
            "args": {"text": overlay_text, "x": 32, "y": 32, "fontSize": 36, "start": 0, "end": 2.5},
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
    max_edits: int | None = None,
) -> dict[str, Any]:
    if _in_test_mode():
        raise RuntimeError("AD_TEST_MODE=1 disables OpenAI planning. Unset AD_TEST_MODE to use OpenAI-only decisions.")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI-only planning.")

    edits = max(1, min(max_edits or DEFAULT_MAX_EDITS, 6))
    audio_segments = analysis.get("audio_segments", []) if isinstance(analysis, dict) else []
    captions = analysis.get("captions", []) if isinstance(analysis, dict) else []
    caption_lines = _compact_lines(captions, "caption", limit=10)
    audio_lines = _compact_lines(audio_segments, "text", limit=10)

    research_summary = _truncate(research.get("insights", "")) if research else ""
    research_citations = research.get("citations", []) if research else []

    user_payload = {
        "audience": audience_description,
        "group_context": context,
        "research_summary": research_summary,
        "research_citations": research_citations,
        "transcript_excerpts": audio_lines,
        "caption_highlights": caption_lines,
        "available_tools": PLANNER_TOOLS,
        "combo_names": COMBOS,
        "speed_tags": SPEED_CHANGE_TAGS,
        "grade_styles": COLOR_GRADE_STYLES,
        "max_transformations": edits,
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
        return {"ok": False, "error": str(exc), "decisions": _heuristic_decisions(context, analysis, context.get("groupId", 0))}

    decisions = plan.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return {"ok": False, "error": plan.get("error", "Planner returned no decisions"), "decisions": _heuristic_decisions(context, analysis, context.get("groupId", 0))}

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
        payload.setdefault("comboName", _recommended_combo(context))
    elif tool == "add_text_overlay_video":
        payload.setdefault("text", _pick_overlay_text(research, analysis))
        payload.setdefault("x", 32)
        payload.setdefault("y", 32)
        payload.setdefault("fontSize", 36)
        payload.setdefault("start", 0)
        payload.setdefault("end", 2.5)
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
    return payload


def _resolve_combo_conflicts(decisions: list[dict[str, Any]]) -> None:
    combo = None
    combo_decision = None
    for decision in decisions:
        if decision.get("tool") == "apply_combo" and decision.get("apply"):
            combo = decision.get("args", {}).get("comboName")
            combo_decision = decision
            break
    if not combo:
        return
    conflicts = COMBO_FEATURES.get(combo, set())
    if combo_decision:
        forced_conflict = any(
            d.get("apply") and d.get("forced") and d.get("tool") in conflicts
            for d in decisions
        )
        if forced_conflict:
            combo_decision["apply"] = False
            combo_decision["applied"] = False
            combo_decision["reason"] = (combo_decision.get("reason") or "") + " Skipped due to forced tool conflict."
            return
    for decision in decisions:
        tool = decision.get("tool")
        if tool == "apply_combo":
            continue
        if tool in conflicts and decision.get("apply"):
            decision["apply"] = False
            decision["applied"] = False
            decision["reason"] = (decision.get("reason") or "") + " Skipped due to combo overlap."


def _apply_decisions(
    video_id: str,
    group_id: int,
    original_path: Path,
    decisions: list[dict[str, Any]],
    processed_dir: Path,
    context: dict[str, Any],
    analysis: dict | None,
    research: dict | None,
) -> tuple[str | None, list[dict[str, Any]]]:
    ordered = {tool: idx for idx, tool in enumerate(PLANNER_ORDER)}
    decisions.sort(key=lambda item: ordered.get(item.get("tool"), 999))

    for decision in decisions:
        if "applied" not in decision:
            decision["applied"] = False

    for decision in decisions:
        if decision.get("tool") == "apply_combo" and decision.get("apply"):
            if decision.get("source") != "ai":
                decision["args"] = _fill_tool_args(
                    "apply_combo", decision.get("args") or {}, context, analysis, research
                )

    _resolve_combo_conflicts(decisions)

    current_input = str(original_path)
    applied_steps = 0
    for decision in decisions:
        if not decision.get("apply"):
            continue
        tool = decision.get("tool")
        if not tool:
            continue

        args = decision.get("args") or {}
        if decision.get("source") != "ai":
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

    for group in groups:
        group_id = group["id"]
        context = group.get("context") or {}
        research = _run_group_research(group["description"], context=context)
        plan = plan_group_transformations(
            group["description"],
            analysis,
            research=research,
            context=context,
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
