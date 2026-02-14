import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from video import speed_up_video

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TOOLS = [
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
        tools=TOOLS,
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
        client.chat.completions.create(model=MODEL, tools=TOOLS, messages=follow_up_messages)

    return {"ok": True, "outputPath": output_path}
