from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from .agent import COLOR_GRADE_STYLES, COMBOS, SPEED_CHANGE_TAGS, _dispatch_tool
from .generative.agent import (
    submit_background_replace,
    submit_object_erase,
    submit_text_replace,
)
from .market_research import run_market_research_agent
from .tool_catalog import BASIC_EDIT_TOOLS, GENERATIVE_TOOLS, MARKET_RESEARCH_TOOLS

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EDIT_TOOL_NAMES = {tool["function"]["name"] for tool in BASIC_EDIT_TOOLS}
GENERATIVE_TOOL_NAMES = {tool["function"]["name"] for tool in GENERATIVE_TOOLS}
RESEARCH_TOOL_NAMES = {tool["function"]["name"] for tool in MARKET_RESEARCH_TOOLS}
ALL_TOOLS = [*BASIC_EDIT_TOOLS, *GENERATIVE_TOOLS, *MARKET_RESEARCH_TOOLS]

SYSTEM_PROMPT = (
    "You are a video orchestration agent. Pick the single best tool for the request. "
    "For speed changes, use change_speed_video or speed_up_video and choose changeTag "
    f"from: {', '.join(SPEED_CHANGE_TAGS)}. If a percent is requested, pick the nearest "
    "tag and explain the mapping in changeNote. Never exceed +/-6%. "
    "For color grading, use color_grade_video with gradeStyle from: "
    f"{', '.join(COLOR_GRADE_STYLES)} and explain the choice in gradeNote. "
    "For generative requests (background replace, object erase, text replace), use the "
    "submit_* tools to run a Lucy video-to-video edit. If using apply_combo, choose comboName from: "
    f"{', '.join(COMBOS)}. For submit_* tools, map inputPath/outputPath to "
    "inputVideo/outputVideo. Always include input/output paths (or use the provided "
    "defaults). If the request is about market research, demographics, or ad preferences, "
    "use market_research and pass audienceDescription plus any product/region/goal details. "
    "If unclear, choose a neutral speed change."
)


def _parse_args(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def _dispatch_generative(name: str, args: dict, input_path: str, output_path: str) -> dict:
    payload = dict(args or {})
    payload.setdefault("inputVideo", input_path)
    payload.setdefault("outputVideo", output_path)

    if name == "submit_background_replace":
        return submit_background_replace(payload)
    if name == "submit_object_erase":
        return submit_object_erase(payload)
    if name == "submit_text_replace":
        return submit_text_replace(payload)
    return {"ok": False, "error": "Unknown generative tool"}


def _dispatch_market_research(args: dict) -> dict:
    return run_market_research_agent(
        audience_description=args.get("audienceDescription") or args.get("audience") or "",
        product=args.get("product"),
        region=args.get("region"),
        goal=args.get("goal"),
        extra_focus=args.get("extraFocus"),
        language=args.get("language"),
    )


def run_orchestrator_agent(
    request: str, input_path: str | None = None, output_path: str | None = None
) -> dict:
    resolved_input = input_path or "N/A"
    resolved_output = output_path or "N/A"
    input_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Request: {request}\n"
                f"inputPath: {resolved_input}\n"
                f"outputPath: {resolved_output}\n"
                "Pick the best tool and execute it."
            ),
        },
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=input_messages,
        tools=ALL_TOOLS,
        tool_choice="required",
    )

    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    outputs = []

    for call in tool_calls:
        if not call.function:
            continue
        args = _parse_args(call.function.arguments)
        name = call.function.name

        if name in EDIT_TOOL_NAMES:
            result = _dispatch_tool(name, args, resolved_input, resolved_output)
        elif name in GENERATIVE_TOOL_NAMES:
            result = _dispatch_generative(name, args, resolved_input, resolved_output)
        elif name in RESEARCH_TOOL_NAMES:
            result = _dispatch_market_research(args)
        else:
            result = {"ok": False, "error": "Unknown tool"}

        outputs.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),
            }
        )

    if outputs:
        follow_up = input_messages + [message.model_dump()] + outputs
        client.chat.completions.create(model=MODEL, tools=ALL_TOOLS, messages=follow_up)

    return outputs[-1] if outputs else {"ok": False, "error": "No tool calls"}
