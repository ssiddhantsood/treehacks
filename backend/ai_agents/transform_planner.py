import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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
        if start == -1 or end == -1:
            return {}
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def _decision_map(decisions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item.get("tool"): item for item in decisions if item.get("tool")}


def _is_slow_tag(tag: str) -> bool:
    return tag in {"slow_2", "slow_4", "slow_6"}


def _visible_count(decisions: list[dict[str, Any]], visible_tools: set[str]) -> int:
    return sum(1 for item in decisions if item.get("apply") and item.get("tool") in visible_tools)


def _missing_tools(decisions: list[dict[str, Any]], tools: list[str]) -> list[str]:
    present = {item.get("tool") for item in decisions if item.get("tool")}
    return [tool for tool in tools if tool not in present]


def _constraint_feedback(
    decisions: list[dict[str, Any]],
    tools: list[str],
    visible_tools: set[str],
    min_visible: int,
    context: dict[str, Any],
) -> list[str]:
    feedback: list[str] = []
    missing = _missing_tools(decisions, tools)
    if missing:
        feedback.append(f"Missing tool decisions: {', '.join(missing)}")

    tool_map = _decision_map(decisions)
    if context.get("timeOfDay") and not tool_map.get("change_speed_video", {}).get("apply"):
        feedback.append("Must apply change_speed_video because timeOfDay is present.")

    if context.get("englishSpeaking") is False:
        speed_args = tool_map.get("change_speed_video", {}).get("args") or {}
        tag = str(speed_args.get("changeTag") or "").strip()
        if not _is_slow_tag(tag):
            feedback.append("Non-English market must use a slow_* speed tag.")

    if not tool_map.get("color_grade_video", {}).get("apply"):
        feedback.append("Must apply color_grade_video for tone/grade.")

    visible = _visible_count(decisions, visible_tools)
    if visible < min_visible:
        feedback.append(f"Need at least {min_visible} visible transforms; only {visible} are applied.")

    return feedback


def _planner_prompt(payload: dict) -> tuple[str, str]:
    system_prompt = (
        "You are an ad transformation planning agent. You must decide for each available tool "
        "whether to apply it for this audience cluster. Provide concrete args when applying. "
        "Bias towards making changes, even if subtle. Tie decisions to time-of-day, region, "
        "language, urbanicity, and demographic context. Use groupId as a tie-breaker to keep "
        "variants distinct. Return JSON only."
    )
    user_prompt = (
        "Return JSON with `decisions` containing one entry per tool in available_tools. "
        "Each decision must include: tool, apply (true/false), reason, summary, args. "
        "Constraints:\n"
        "- If timeOfDay is present, change_speed_video must apply.\n"
        "- If englishSpeaking is false, change_speed_video must use slow_* tag.\n"
        "- color_grade_video must apply.\n"
        "- At least min_visible visible transforms must apply.\n"
        "When apply=true, include required args for the tool.\n\n"
        + json.dumps(payload)
    )
    return system_prompt, user_prompt


def _review_prompt(payload: dict, decisions: list[dict[str, Any]], feedback: list[str]) -> tuple[str, str]:
    system_prompt = (
        "You are a strict compliance reviewer. Fix the decisions so they satisfy all constraints. "
        "Keep decisions concise and grounded in the provided context. Return JSON only."
    )
    user_prompt = (
        "Given the payload and current decisions, correct them so they meet all constraints. "
        "Do not drop any tools; every tool must appear exactly once.\n"
        f"Feedback: {feedback}\n\n"
        + json.dumps(
            {
                "payload": payload,
                "decisions": decisions,
            }
        )
    )
    return system_prompt, user_prompt


def plan_with_review(
    payload: dict,
    tools: list[str],
    visible_tools: set[str],
    min_visible: int,
    context: dict[str, Any],
    max_rounds: int = 3,
) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        return {"ok": False, "error": "Missing OPENAI_API_KEY", "decisions": []}

    system_prompt, user_prompt = _planner_prompt(payload)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.25,
    )

    raw = response.choices[0].message.content or ""
    payload_out = _extract_json(raw)
    decisions = payload_out.get("decisions") if isinstance(payload_out, dict) else None
    if not isinstance(decisions, list):
        return {"ok": False, "error": "Planner returned invalid JSON", "raw": raw, "decisions": []}

    for _ in range(max_rounds):
        feedback = _constraint_feedback(decisions, tools, visible_tools, min_visible, context)
        if not feedback:
            return {"ok": True, "model": MODEL, "raw": raw, "decisions": decisions}

        review_system, review_user = _review_prompt(payload, decisions, feedback)
        review = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": review_system},
                {"role": "user", "content": review_user},
            ],
            temperature=0.2,
        )
        raw = review.choices[0].message.content or ""
        payload_out = _extract_json(raw)
        decisions = payload_out.get("decisions") if isinstance(payload_out, dict) else None
        if not isinstance(decisions, list):
            return {"ok": False, "error": "Reviewer returned invalid JSON", "raw": raw, "decisions": []}

    return {
        "ok": False,
        "error": "Planner could not satisfy constraints after review.",
        "raw": raw,
        "decisions": decisions,
    }
