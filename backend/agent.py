import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from video import (
    apply_combo,
    change_speed_video,
    color_grade_video,
    reverse_video,
    speed_up_video,
    trim_video,
)

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SPEED_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "speed_up_video",
            "description": "Speed up a video by a given factor and write it to a new path.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inputPath": {
                        "type": "string",
                        "description": "Absolute path to the source video file.",
                    },
                    "outputPath": {
                        "type": "string",
                        "description": "Absolute path for the output video file.",
                    },
                    "factor": {
                        "type": "number",
                        "description": "Speed factor (e.g. 1.05 for +5%).",
                    },
                },
                "required": ["inputPath", "outputPath", "factor"],
            },
        },
    }
]

SYSTEM_PROMPT = (
    "You are a video processing agent. "
    "Always call the speed_up_video tool to perform the work."
)

COMBOS = ["warm_boost", "cool_slow", "punchy_trim", "reverse_pop"]

EDIT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "change_speed_video",
            "description": "Change the speed of a video by a factor (e.g. 1.1 faster, 0.9 slower).",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inputPath": {"type": "string"},
                    "outputPath": {"type": "string"},
                    "factor": {"type": "number"},
                },
                "required": ["inputPath", "outputPath", "factor"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "color_grade_video",
            "description": "Apply basic color grading via contrast/brightness/saturation.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inputPath": {"type": "string"},
                    "outputPath": {"type": "string"},
                    "contrast": {"type": "number"},
                    "brightness": {"type": "number"},
                    "saturation": {"type": "number"},
                },
                "required": ["inputPath", "outputPath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trim_video",
            "description": "Trim a segment from a video.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inputPath": {"type": "string"},
                    "outputPath": {"type": "string"},
                    "start": {"type": "number"},
                    "duration": {"type": "number"},
                },
                "required": ["inputPath", "outputPath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reverse_video",
            "description": "Reverse a video (and audio if present).",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inputPath": {"type": "string"},
                    "outputPath": {"type": "string"},
                },
                "required": ["inputPath", "outputPath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_combo",
            "description": "Apply a predefined combo of edits.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inputPath": {"type": "string"},
                    "outputPath": {"type": "string"},
                    "comboName": {"type": "string"},
                },
                "required": ["inputPath", "outputPath", "comboName"],
            },
        },
    },
]


def _parse_args(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def _dispatch_tool(name: str, args: dict, input_path: str, output_path: str) -> dict:
    resolved_input = args.get("inputPath") or input_path
    resolved_output = args.get("outputPath") or output_path

    if name == "change_speed_video":
        factor = args.get("factor", 1.0)
        change_speed_video(resolved_input, resolved_output, float(factor))
    elif name == "color_grade_video":
        color_grade_video(
            resolved_input,
            resolved_output,
            contrast=float(args.get("contrast", 1.1)),
            brightness=float(args.get("brightness", 0.03)),
            saturation=float(args.get("saturation", 1.15)),
        )
    elif name == "trim_video":
        trim_video(
            resolved_input,
            resolved_output,
            start=float(args.get("start", 0.0)),
            duration=float(args.get("duration", 6.0)),
        )
    elif name == "reverse_video":
        reverse_video(resolved_input, resolved_output)
    elif name == "apply_combo":
        combo = args.get("comboName") or "warm_boost"
        apply_combo(resolved_input, resolved_output, combo)
    elif name == "speed_up_video":
        factor = args.get("factor", 1.05)
        speed_up_video(resolved_input, resolved_output, float(factor))
    else:
        raise ValueError(f"Unknown tool: {name}")

    return {"ok": True, "outputPath": resolved_output}


def run_speedup_agent(input_path: str, output_path: str, factor: float = 1.05) -> dict:
    input_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Speed up the video by factor {factor}. "
                f"Use inputPath {input_path} and outputPath {output_path}."
            ),
        },
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=input_messages,
        tools=SPEED_TOOLS,
        tool_choice="required",
    )

    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    function_outputs = []

    for item in tool_calls:
        if item.function and item.function.name == "speed_up_video":
            try:
                args = json.loads(item.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            resolved_input = args.get("inputPath") or input_path
            resolved_output = args.get("outputPath") or output_path
            resolved_factor = args.get("factor")

            if not isinstance(resolved_factor, (int, float)):
                resolved_factor = factor

            speed_up_video(resolved_input, resolved_output, resolved_factor)

            function_outputs.append(
                {
                    "role": "tool",
                    "tool_call_id": item.id,
                    "content": json.dumps({"ok": True, "outputPath": resolved_output}),
                }
            )

    if function_outputs:
        follow_up_messages = input_messages + [message.model_dump()] + function_outputs
        client.chat.completions.create(model=MODEL, tools=SPEED_TOOLS, messages=follow_up_messages)

    return {"ok": True, "outputPath": output_path}


def run_combo_agent(input_path: str, output_path: str, combo_name: str) -> dict:
    input_messages = [
        {
            "role": "system",
            "content": (
                "You are a video edit agent. You must call the apply_combo tool "
                "exactly once using one of the predefined combo names."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Apply combo '{combo_name}' to the video. "
                f"Use inputPath {input_path} and outputPath {output_path}. "
                f"Available combos: {', '.join(COMBOS)}."
            ),
        },
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=input_messages,
        tools=EDIT_TOOLS,
        tool_choice="required",
    )

    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    function_outputs = []

    for item in tool_calls:
        if not item.function:
            continue
        args = _parse_args(item.function.arguments)
        result = _dispatch_tool(item.function.name, args, input_path, output_path)
        function_outputs.append(
            {
                "role": "tool",
                "tool_call_id": item.id,
                "content": json.dumps(result),
            }
        )

    if function_outputs:
        follow_up = input_messages + [message.model_dump()] + function_outputs
        client.chat.completions.create(model=MODEL, tools=EDIT_TOOLS, messages=follow_up)

    return {"ok": True, "outputPath": output_path}
