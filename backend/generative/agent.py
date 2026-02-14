import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

JOBS_DIR = Path(__file__).resolve().parent / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_background_replace",
            "description": "Create a background replacement job spec.",
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
            "description": "Create an object erase job spec.",
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
            "description": "Create a text replacement job spec.",
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
    "Always call the appropriate tool to create a job spec."
)


def _write_job(job_type: str, payload: dict) -> dict:
    job_id = uuid4().hex
    job = {"id": job_id, "job_type": job_type, **payload}
    job_path = JOBS_DIR / f"{job_id}.json"
    job_path.write_text(json.dumps(job, indent=2))
    return {"ok": True, "job_id": job_id, "job_path": str(job_path)}


def submit_background_replace(args: dict) -> dict:
    return _write_job("background_replace", args)


def submit_object_erase(args: dict) -> dict:
    return _write_job("object_erase", args)


def submit_text_replace(args: dict) -> dict:
    return _write_job("text_replace", args)


def run_generative_agent(request: str, input_video: str, output_video: str) -> dict:
    input_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Request: {request}\n"
                f"inputVideo: {input_video}\n"
                f"outputVideo: {output_video}\n"
                "Create the best job spec using the available tools."
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
