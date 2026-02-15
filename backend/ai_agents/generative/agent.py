import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
LUCY_VIDEO_TO_VIDEO_URL = os.getenv("LUCY_VIDEO_TO_VIDEO_URL", "http://localhost:8000/gpu/edit")
LUCY_MODEL_ID = os.getenv("LUCY_MODEL_ID", "decart-ai/Lucy-Edit-Dev")
LUCY_NUM_FRAMES = int(os.getenv("LUCY_NUM_FRAMES", "81"))
LUCY_HEIGHT = int(os.getenv("LUCY_HEIGHT", "480"))
LUCY_WIDTH = int(os.getenv("LUCY_WIDTH", "832"))
LUCY_GUIDANCE_SCALE = float(os.getenv("LUCY_GUIDANCE_SCALE", "7.0"))
LUCY_STRENGTH = float(os.getenv("LUCY_STRENGTH", "0.85"))
LUCY_NUM_INFERENCE_STEPS = int(os.getenv("LUCY_NUM_INFERENCE_STEPS", "40"))
LUCY_FPS = int(os.getenv("LUCY_FPS", "24"))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_background_replace",
            "description": "Run a Lucy video-to-video background replacement.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inputVideo": {"type": "string"},
                    "outputVideo": {"type": "string"},
                    "prompt": {"type": "string"},
                    "backgroundImage": {"type": "string"},
                    "subject": {"type": "string"},
                    "seed": {"type": "integer"},
                },
                "required": ["inputVideo", "outputVideo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_object_erase",
            "description": "Run a Lucy video-to-video object erase.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inputVideo": {"type": "string"},
                    "outputVideo": {"type": "string"},
                    "objectPrompt": {"type": "string"},
                    "boxThreshold": {"type": "number"},
                    "textThreshold": {"type": "number"},
                    "seed": {"type": "integer"},
                },
                "required": ["inputVideo", "outputVideo", "objectPrompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_text_replace",
            "description": "Run a Lucy video-to-video text replacement.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "inputVideo": {"type": "string"},
                    "outputVideo": {"type": "string"},
                    "targetText": {"type": "string"},
                    "newText": {"type": "string"},
                    "fontPath": {"type": "string"},
                    "fontSize": {"type": "integer"},
                    "color": {"type": "string"},
                    "seed": {"type": "integer"},
                },
                "required": ["inputVideo", "outputVideo", "newText"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are a generative video agent. "
    "Always call the appropriate tool to run a Lucy video-to-video edit."
)

def _ensure_curl() -> str | None:
    return shutil.which("curl")


def _lucy_payload(prompt: str, video_url: str, seed: int | None) -> dict:
    payload = {
        "video_url": video_url,
        "prompt": prompt,
        "negative_prompt": "",
        "num_frames": LUCY_NUM_FRAMES,
        "height": LUCY_HEIGHT,
        "width": LUCY_WIDTH,
        "guidance_scale": LUCY_GUIDANCE_SCALE,
        "strength": LUCY_STRENGTH,
        "num_inference_steps": LUCY_NUM_INFERENCE_STEPS,
        "fps": LUCY_FPS,
        "model_id": LUCY_MODEL_ID,
    }
    if seed is not None:
        payload["seed"] = int(seed)
    return payload


def _call_lucy(payload: dict, output_path: str) -> dict:
    curl_path = _ensure_curl()
    if not curl_path:
        return {"ok": False, "error": "curl is required but was not found on PATH"}

    if not LUCY_VIDEO_TO_VIDEO_URL:
        return {"ok": False, "error": "LUCY_VIDEO_TO_VIDEO_URL is not configured"}

    request_body = json.dumps(payload)
    result = subprocess.run(
        [
            curl_path,
            "-sS",
            "-X",
            "POST",
            LUCY_VIDEO_TO_VIDEO_URL,
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ],
        input=request_body,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        return {
            "ok": False,
            "error": "Lucy request failed",
            "detail": (result.stderr or result.stdout).strip(),
        }

    try:
        response = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "Lucy returned invalid JSON", "detail": result.stdout.strip()}

    if response.get("status") != "success":
        return {
            "ok": False,
            "error": response.get("error") or "Lucy returned an error",
            "lucy": {k: v for k, v in response.items() if k != "video_base64"},
        }

    video_base64 = response.get("video_base64")
    if not video_base64:
        return {"ok": False, "error": "Lucy response missing video_base64"}

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_file.write_bytes(base64.b64decode(video_base64))
    except Exception as exc:
        return {"ok": False, "error": f"Failed to write output video: {exc}"}

    slim = {k: v for k, v in response.items() if k != "video_base64"}
    return {"ok": True, "outputPath": str(output_file), "lucy": slim}


def _build_background_prompt(args: dict) -> str:
    prompt = (args.get("prompt") or "").strip()
    background_image = (args.get("backgroundImage") or "").strip()
    subject = (args.get("subject") or "").strip()

    if prompt:
        base = f"Replace the background with {prompt}."
    else:
        base = "Replace the background."

    if subject:
        base += f" Keep the {subject} intact."
    else:
        base += " Keep the main subject intact."

    if background_image:
        base += f" Match this reference: {background_image}."

    return base


def _build_object_erase_prompt(args: dict) -> str:
    target = (args.get("objectPrompt") or "").strip()
    if target:
        return f"Remove the {target} from the video. Fill the area naturally."
    return "Remove the unwanted object from the video. Fill the area naturally."


def _build_text_replace_prompt(args: dict) -> str:
    target_text = (args.get("targetText") or "").strip()
    new_text = (args.get("newText") or "").strip()
    font_path = (args.get("fontPath") or "").strip()
    font_size = args.get("fontSize")
    color = (args.get("color") or "").strip()

    if target_text and new_text:
        base = f"Replace the text '{target_text}' with '{new_text}'."
    elif new_text:
        base = f"Add or replace on-screen text with '{new_text}'."
    else:
        base = "Replace on-screen text."

    if font_size:
        base += f" Use font size {int(font_size)}."
    if color:
        base += f" Use color {color}."
    if font_path:
        base += f" Match the font from {font_path}."
    return base


def submit_background_replace(args: dict) -> dict:
    prompt = _build_background_prompt(args)
    video_url = args.get("inputVideo") or ""
    if not video_url:
        return {"ok": False, "error": "inputVideo is required"}
    output_video = args.get("outputVideo") or ""
    if not output_video:
        return {"ok": False, "error": "outputVideo is required"}
    payload = _lucy_payload(prompt, video_url, args.get("seed"))
    return _call_lucy(payload, output_video)


def submit_object_erase(args: dict) -> dict:
    prompt = _build_object_erase_prompt(args)
    video_url = args.get("inputVideo") or ""
    if not video_url:
        return {"ok": False, "error": "inputVideo is required"}
    output_video = args.get("outputVideo") or ""
    if not output_video:
        return {"ok": False, "error": "outputVideo is required"}
    payload = _lucy_payload(prompt, video_url, args.get("seed"))
    return _call_lucy(payload, output_video)


def submit_text_replace(args: dict) -> dict:
    prompt = _build_text_replace_prompt(args)
    video_url = args.get("inputVideo") or ""
    if not video_url:
        return {"ok": False, "error": "inputVideo is required"}
    output_video = args.get("outputVideo") or ""
    if not output_video:
        return {"ok": False, "error": "outputVideo is required"}
    payload = _lucy_payload(prompt, video_url, args.get("seed"))
    return _call_lucy(payload, output_video)


def run_generative_agent(request: str, input_video: str, output_video: str) -> dict:
    input_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Request: {request}\n"
                f"inputVideo: {input_video}\n"
                f"outputVideo: {output_video}\n"
                "Run the best Lucy edit using the available tools."
            ),
        },
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=input_messages,
        tools=TOOLS,
        tool_choice="required",
    )

    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    outputs = []

    for call in tool_calls:
        if not call.function:
            continue
        args = json.loads(call.function.arguments or "{}")
        if call.function.name == "submit_background_replace":
            result = submit_background_replace(args)
        elif call.function.name == "submit_object_erase":
            result = submit_object_erase(args)
        elif call.function.name == "submit_text_replace":
            result = submit_text_replace(args)
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
        client.chat.completions.create(model=MODEL, tools=TOOLS, messages=follow_up)

    return outputs[-1] if outputs else {"ok": False, "error": "No tool calls"}
