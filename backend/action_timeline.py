import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

load_dotenv()

VLM_MODEL = os.getenv("OPENAI_VLM_MODEL", "gpt-4.1-mini")
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
ASR_MODEL = os.getenv("OPENAI_ASR_MODEL", "gpt-4o-mini-transcribe")

FPS = float(os.getenv("ACTION_FPS", "2"))
DIFF_THRESHOLD = float(os.getenv("ACTION_DIFF_THRESHOLD", "0.12"))
MIN_KEYFRAME_GAP = float(os.getenv("ACTION_MIN_KEYFRAME_GAP", "0.5"))
MAX_KEYFRAME_GAP = float(os.getenv("ACTION_MAX_KEYFRAME_GAP", "6"))
BG_UPDATE_SEC = float(os.getenv("ACTION_BG_UPDATE_SEC", "5"))
BG_WINDOW_SEC = float(os.getenv("ACTION_BG_WINDOW_SEC", "10"))
INCLUDE_AUDIO = os.getenv("ACTION_INCLUDE_AUDIO", "1") == "1"
FRAME_SCALE = int(os.getenv("ACTION_FRAME_SCALE", "512"))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _get_duration(video_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())


def _extract_frames(video_path: str, frames_dir: Path) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-vf",
        f"fps={FPS},scale={FRAME_SCALE}:-1",
        "-q:v",
        "3",
        str(frames_dir / "%06d.jpg"),
    ]
    _run(cmd)


def _extract_audio(video_path: str, audio_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ]
    _run(cmd)


def _frame_signature(path: Path) -> np.ndarray:
    img = Image.open(path).convert("L").resize((48, 48))
    arr = np.array(img, dtype=np.float32) / 255.0
    return arr


def _diff_score(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def _image_to_data_url(path: Path) -> str:
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def _caption_frame(image_path: Path, known_entities: list[str]) -> dict:
    system_prompt = (
        "You are a vision model that describes visible actions. "
        "Be concise and grounded in what is visible."
    )
    user_text = (
        "Describe the current frame with 1-2 short sentences focused on actions. "
        "If you reference people or objects, keep names consistent with known_entities. "
        "Return valid JSON with keys: caption, actions, objects, people, setting, confidence. "
        "confidence is 0-1. actions/objects/people are arrays of short strings."
    )
    if known_entities:
        user_text += f" Known entities: {', '.join(known_entities)}."

    response = client.chat.completions.create(
        model=VLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": _image_to_data_url(image_path)}},
                ],
            },
        ],
    )

    content = response.choices[0].message.content or "{}"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = {
            "caption": content.strip(),
            "actions": [],
            "objects": [],
            "people": [],
            "setting": "",
            "confidence": 0.3,
        }
    return payload


def _transcribe_audio(audio_path: Path) -> list[dict]:
    response_format = "verbose_json" if ASR_MODEL == "whisper-1" else "json"
    extra_args = {}
    if response_format == "verbose_json":
        extra_args["timestamp_granularities"] = ["segment"]

    with audio_path.open("rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=ASR_MODEL,
            file=audio_file,
            response_format=response_format,
            **extra_args,
        )

    segments = []
    raw_segments = getattr(transcript, "segments", None) or []

    for segment in raw_segments:
        if isinstance(segment, dict):
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", 0.0))
            text = (segment.get("text") or "").strip()
        else:
            start = float(getattr(segment, "start", 0.0))
            end = float(getattr(segment, "end", 0.0))
            text = (getattr(segment, "text", "") or "").strip()

        if text:
            segments.append({"start": start, "end": end, "text": text})

    if segments:
        return segments

    fallback_text = (getattr(transcript, "text", "") or "").strip()
    if fallback_text:
        return [{"start": 0.0, "end": 0.0, "text": fallback_text}]

    return []


def _summarize_background(
    window_captions: list[dict],
    window_audio: list[dict],
    state: dict,
) -> tuple[str, dict]:
    caption_lines = [c["caption"] for c in window_captions if c.get("caption")]
    audio_lines = [s["text"] for s in window_audio if s.get("text")]

    system_prompt = (
        "You summarize ongoing video context based on recent visual actions and audio. "
        "Keep it to 1-2 sentences and avoid repeating static details."
    )

    user_prompt = {
        "previous_summary": state.get("summary", ""),
        "known_entities": state.get("entities", []),
        "recent_captions": caption_lines,
        "recent_audio": audio_lines,
    }

    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt)},
        ],
    )

    summary = (response.choices[0].message.content or "").strip()
    new_entities = state.get("entities", [])

    return summary, {"summary": summary, "entities": new_entities}


def analyze_video(video_path: str, output_json_path: str) -> dict:
    video_path = str(video_path)
    output_path = Path(output_json_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        frames_dir = tmp_path / "frames"
        audio_path = tmp_path / "audio.wav"

        duration = _get_duration(video_path)
        _extract_frames(video_path, frames_dir)

        if INCLUDE_AUDIO:
            _extract_audio(video_path, audio_path)
            audio_segments = _transcribe_audio(audio_path)
        else:
            audio_segments = []

        frame_files = sorted(frames_dir.glob("*.jpg"))
        captions = []
        events = []
        known_entities: list[str] = []

        prev_signature = None
        last_caption_time = -999.0
        last_caption_id = None
        segment_start = 0.0

        for index, frame_path in enumerate(frame_files):
            timestamp = index / FPS
            signature = _frame_signature(frame_path)

            needs_update = False
            if prev_signature is None:
                needs_update = True
            else:
                diff = _diff_score(signature, prev_signature)
                since_last = timestamp - last_caption_time
                if diff >= DIFF_THRESHOLD and since_last >= MIN_KEYFRAME_GAP:
                    needs_update = True
                if since_last >= MAX_KEYFRAME_GAP:
                    needs_update = True

            if needs_update:
                payload = _caption_frame(frame_path, known_entities)
                caption_id = len(captions)
                caption = {
                    "id": caption_id,
                    "t": round(timestamp, 3),
                    "caption": payload.get("caption", "").strip(),
                    "actions": payload.get("actions", []),
                    "objects": payload.get("objects", []),
                    "people": payload.get("people", []),
                    "setting": payload.get("setting", ""),
                    "confidence": payload.get("confidence", 0.0),
                }
                captions.append(caption)

                for item in caption["people"] + caption["objects"]:
                    if item and item not in known_entities:
                        known_entities.append(item)

                if last_caption_id is not None:
                    events.append(
                        {
                            "t_start": round(segment_start, 3),
                            "t_end": round(timestamp, 3),
                            "caption_id": last_caption_id,
                        }
                    )
                segment_start = timestamp
                last_caption_id = caption_id
                last_caption_time = timestamp
                prev_signature = signature
            else:
                prev_signature = signature

        if last_caption_id is not None:
            events.append(
                {
                    "t_start": round(segment_start, 3),
                    "t_end": round(duration, 3),
                    "caption_id": last_caption_id,
                }
            )

        background_updates = []
        state = {"summary": "", "entities": known_entities}
        last_caption_marker = -1
        last_audio_marker = -1

        if captions or audio_segments:
            t = 0.0
            while t <= duration:
                window_start = max(0.0, t - BG_WINDOW_SEC)
                window_captions = [c for c in captions if window_start <= c["t"] <= t]
                window_audio = [s for s in audio_segments if s["end"] >= window_start and s["start"] <= t]

                newest_caption_id = window_captions[-1]["id"] if window_captions else -1
                newest_audio_idx = audio_segments.index(window_audio[-1]) if window_audio else -1

                if newest_caption_id != last_caption_marker or newest_audio_idx != last_audio_marker:
                    summary, state = _summarize_background(window_captions, window_audio, state)
                    if summary:
                        background_updates.append({"t": round(t, 3), "narration": summary})
                    last_caption_marker = newest_caption_id
                    last_audio_marker = newest_audio_idx

                t += BG_UPDATE_SEC

        result = {
            "fps": FPS,
            "duration": round(duration, 3),
            "captions": captions,
            "events": events,
            "background_updates": background_updates,
            "audio_segments": audio_segments,
        }

        output_path.write_text(json.dumps(result, indent=2))
        return result
