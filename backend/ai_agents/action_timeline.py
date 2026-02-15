import base64
import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
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
SCENE_THRESHOLD = float(os.getenv("ACTION_SCENE_THRESHOLD", "0.3"))
DENSE_INTERVAL = float(os.getenv("ACTION_DENSE_INTERVAL", "0.5"))
PER_SECOND_FPS = float(os.getenv("ACTION_PER_SECOND_FPS", "1"))
SCENE_SAMPLE_COUNT = int(os.getenv("ACTION_SCENE_SAMPLE_COUNT", "3"))
JUSTIFY_CHUNK_SEC = float(os.getenv("ACTION_JUSTIFY_CHUNK_SEC", "60"))
def _coerce_int(value, default: int, min_value: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, parsed)


VLM_CONCURRENCY = _coerce_int(os.getenv("ACTION_VLM_CONCURRENCY", "4"), 4, 1)

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


def _parallel_map(items: list, func, max_workers: int) -> list:
    if max_workers <= 1 or len(items) <= 1:
        return [func(item) for item in items]
    results = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {executor.submit(func, item): idx for idx, item in enumerate(items)}
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            results[idx] = future.result()
    return results


def _image_to_data_url(path: Path) -> str:
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def _detect_scene_cuts(video_path: str) -> list[float]:
    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-an",
        "-sn",
        "-dn",
        "-vf",
        f"select='gt(scene,{SCENE_THRESHOLD})',showinfo",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []

    timestamps = []
    for line in result.stderr.splitlines():
        if "pts_time:" not in line:
            continue
        match = re.search(r"pts_time:(\d+(?:\.\d+)?)", line)
        if not match:
            continue
        timestamps.append(float(match.group(1)))

    if not timestamps:
        return []

    rounded = [round(t, 3) for t in timestamps]
    seen = set()
    deduped = []
    for value in rounded:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _frame_index_for_timestamp(timestamp: float, frame_count: int) -> int:
    if frame_count <= 0:
        return 0
    index = int(round(timestamp * FPS))
    return max(0, min(frame_count - 1, index))


def _caption_frames_at_times(
    frame_files: list[Path],
    timestamps: list[float],
    known_entities: list[str],
) -> list[dict]:
    if not frame_files or not timestamps:
        return []

    requests: list[tuple[float, Path]] = []
    last_index = None
    frame_count = len(frame_files)

    for timestamp in timestamps:
        index = _frame_index_for_timestamp(timestamp, frame_count)
        if index == last_index:
            continue
        requests.append((timestamp, frame_files[index]))
        last_index = index

    def _run(request: tuple[float, Path]) -> dict:
        t_value, frame_path = request
        payload = _caption_frame(frame_path, known_entities)
        return {"t": round(t_value, 3), **payload}

    return _parallel_map(requests, _run, VLM_CONCURRENCY)


def _strip_code_fences(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_json_object(text: str) -> str:
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


def _extract_caption_field(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r'"caption"\s*:\s*"([^"]+)"',
        r"'caption'\s*:\s*'([^']+)'",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def _extract_json_field(text: str, field: str) -> str:
    if not text or not field:
        return ""
    escaped = re.escape(field)
    patterns = [
        rf'"{escaped}"\s*:\s*"([^"]+)"',
        rf"'{escaped}'\s*:\s*'([^']+)'",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def _fallback_caption_text(text: str) -> str:
    cleaned = _strip_code_fences(text)
    extracted = _extract_caption_field(cleaned)
    return extracted or cleaned


def _fallback_text(text: str) -> str:
    return _strip_code_fences(text or "").strip()


def _coerce_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [value]
    else:
        items = [str(value)]

    seen = set()
    output = []
    for item in items:
        if item is None:
            continue
        label = str(item).strip()
        if not label or label in seen:
            continue
        seen.add(label)
        output.append(label)
    return output


def _coerce_setting(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(parts)
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _coerce_confidence(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _parse_caption_payload(content: str) -> tuple[dict, str]:
    cleaned = _strip_code_fences(content or "")
    for candidate in (cleaned, _extract_json_object(cleaned)):
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload, cleaned
    return {}, cleaned


def _normalize_caption_payload(payload: dict, fallback_caption: str) -> dict:
    caption_text = _fallback_caption_text(str(payload.get("caption") or fallback_caption or ""))
    return {
        "caption": caption_text,
        "actions": _coerce_list(payload.get("actions")),
        "objects": _coerce_list(payload.get("objects")),
        "people": _coerce_list(payload.get("people")),
        "setting": _coerce_setting(payload.get("setting")),
        "confidence": _coerce_confidence(payload.get("confidence")),
    }


def _normalize_description_payload(payload: dict, fallback_text: str) -> dict:
    description = payload.get("description") or payload.get("caption") or ""
    if isinstance(description, (dict, list)):
        description = json.dumps(description)
    description = str(description or "").strip()

    if not description:
        extracted = _extract_json_field(fallback_text, "description")
        description = extracted or _fallback_text(fallback_text)

    if description.lower() in {"unknown", "unclear", "n/a", "not sure"}:
        description = ""

    return {
        "description": description,
        "actions": _coerce_list(payload.get("actions")),
        "objects": _coerce_list(payload.get("objects")),
        "people": _coerce_list(payload.get("people")),
        "setting": _coerce_setting(payload.get("setting")),
        "confidence": _coerce_confidence(payload.get("confidence")),
    }


def _caption_frame(image_path: Path, known_entities: list[str]) -> dict:
    system_prompt = (
        "You are a vision model that describes visible actions. "
        "Be concise and grounded in what is visible."
    )
    user_text = (
        "Describe the current frame with 1-2 short sentences focused on actions. "
        "If you reference people or objects, keep names consistent with known_entities. "
        "Return ONLY valid JSON with keys: caption, actions, objects, people, setting, confidence. "
        "Do not wrap in code fences or add extra text. "
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

    content = response.choices[0].message.content or ""
    payload, cleaned = _parse_caption_payload(content)
    if not isinstance(payload, dict):
        payload = {}
    return _normalize_caption_payload(payload, cleaned)


def _describe_frame(image_path: Path, known_entities: list[str]) -> dict:
    system_prompt = (
        "You are a vision model that describes the scene succinctly. "
        "Be precise and avoid guessing."
    )
    user_text = (
        "Describe the overall scene in 1 short sentence. "
        "Focus on what's visible and what's happening. "
        "If something is unknown, leave it out. "
        "Return ONLY valid JSON with keys: description, actions, objects, people, setting, confidence. "
        "Do not wrap in code fences or add extra text. "
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

    content = response.choices[0].message.content or ""
    payload, cleaned = _parse_caption_payload(content)
    if not isinstance(payload, dict):
        payload = {}
    return _normalize_description_payload(payload, cleaned)


def _describe_frames_at_times(
    frame_files: list[Path],
    timestamps: list[float],
    known_entities: list[str],
) -> list[dict]:
    if not frame_files or not timestamps:
        return []

    requests: list[tuple[float, Path]] = []
    last_index = None
    frame_count = len(frame_files)

    for timestamp in timestamps:
        index = _frame_index_for_timestamp(timestamp, frame_count)
        if index == last_index:
            continue
        requests.append((timestamp, frame_files[index]))
        last_index = index

    def _run(request: tuple[float, Path]) -> dict:
        t_value, frame_path = request
        payload = _describe_frame(frame_path, known_entities)
        return {"t": round(t_value, 3), **payload}

    return _parallel_map(requests, _run, VLM_CONCURRENCY)


def _sample_segment_times(start: float, end: float, count: int) -> list[float]:
    if end <= start:
        return [start]
    if count <= 1:
        return [start + (end - start) * 0.5]
    step = (end - start) / count
    samples = [start + (i + 0.5) * step for i in range(count)]
    deduped = []
    seen = set()
    for t in samples:
        rounded = round(t, 3)
        if rounded in seen:
            continue
        seen.add(rounded)
        deduped.append(t)
    return deduped


def _normalize_scene_payload(payload: dict, fallback_text: str) -> dict:
    description = payload.get("description") or ""
    if isinstance(description, (dict, list)):
        description = json.dumps(description)
    description = str(description or "").strip()
    if not description:
        description = _extract_json_field(fallback_text, "description") or _fallback_text(fallback_text)
    if description.lower() in {"unknown", "unclear", "n/a", "not sure"}:
        description = ""

    return {
        "description": description,
        "key_elements": _coerce_list(payload.get("key_elements") or payload.get("elements")),
        "confidence": _coerce_confidence(payload.get("confidence")),
    }


def _describe_scene_segment(
    frame_paths: list[Path],
    known_entities: list[str],
    t_start: float,
    t_end: float,
) -> dict:
    system_prompt = (
        "You describe a single camera angle segment of a video. "
        "Use only what is visible across the provided frames."
    )
    user_text = (
        f"These frames come from the same camera angle between {t_start:.3f}s and {t_end:.3f}s. "
        "Explain what's there and what's going on in 1-2 sentences. "
        "If something is unknown, leave it out. "
        "Return ONLY valid JSON with keys: description, key_elements, confidence. "
        "Do not wrap in code fences or add extra text. "
        "key_elements is an array of short strings."
    )
    if known_entities:
        user_text += f" Known entities: {', '.join(known_entities)}."

    content_parts = [{"type": "text", "text": user_text}]
    for frame in frame_paths:
        content_parts.append({"type": "image_url", "image_url": {"url": _image_to_data_url(frame)}})

    response = client.chat.completions.create(
        model=VLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_parts},
        ],
    )

    content = response.choices[0].message.content or ""
    payload, cleaned = _parse_caption_payload(content)
    if not isinstance(payload, dict):
        payload = {}
    return _normalize_scene_payload(payload, cleaned)


def _extract_json_array(text: str) -> str:
    if not text:
        return ""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


def _parse_json_list(content: str) -> list:
    cleaned = _strip_code_fences(content or "")
    for candidate in (cleaned, _extract_json_array(cleaned), _extract_json_object(cleaned)):
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("justifications") or payload.get("timeline")
            if isinstance(items, list):
                return items
    return []


def _justify_chunk(
    seconds: list[dict],
    scene_segments: list[dict],
    audio_segments: list[dict],
    chunk_start: float,
    chunk_end: float,
) -> list[dict]:
    if not seconds:
        return []

    system_prompt = (
        "You are analyzing an advertisement video. "
        "For each second, justify why that moment is likely included. "
        "Be specific, grounded in the provided visual/audio evidence, and concise. "
        "If you cannot justify a second, return an empty string for its justification."
    )

    user_payload = {
        "chunk_start": round(chunk_start, 3),
        "chunk_end": round(chunk_end, 3),
        "seconds": seconds,
        "scene_segments": scene_segments,
        "audio_segments": audio_segments,
        "instructions": (
            "Return ONLY valid JSON as an array of objects with keys: t, justification. "
            "Use the same t values provided in seconds. Do not add extra text."
        ),
    }

    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
    )

    items = _parse_json_list(response.choices[0].message.content or "")
    allowed = {round(float(item.get("t", 0.0)), 3) for item in seconds if "t" in item}
    justification_map = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            t_value = round(float(item.get("t", 0.0)), 3)
        except (TypeError, ValueError):
            continue
        if t_value not in allowed:
            continue
        text = str(item.get("justification") or "").strip()
        justification_map[t_value] = text

    timeline = []
    for item in seconds:
        try:
            t_value = round(float(item.get("t", 0.0)), 3)
        except (TypeError, ValueError):
            continue
        timeline.append({"t": t_value, "justification": justification_map.get(t_value, "")})
    return timeline


def _build_justification_timeline(
    per_second_descriptions: list[dict],
    scene_segments: list[dict],
    audio_segments: list[dict],
    duration: float,
) -> list[dict]:
    if not per_second_descriptions:
        return []

    timeline = []
    chunk = max(1.0, float(JUSTIFY_CHUNK_SEC))
    t = 0.0
    while t <= duration:
        chunk_start = t
        chunk_end = min(duration, t + chunk)
        seconds = [s for s in per_second_descriptions if chunk_start <= s["t"] <= chunk_end]
        scenes = [
            s
            for s in scene_segments
            if s.get("t_end", 0.0) >= chunk_start and s.get("t_start", 0.0) <= chunk_end
        ]
        audio = [
            s
            for s in audio_segments
            if s.get("end", 0.0) >= chunk_start and s.get("start", 0.0) <= chunk_end
        ]

        timeline.extend(_justify_chunk(seconds, scenes, audio, chunk_start, chunk_end))
        t += chunk

    return timeline


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
        scene_cuts = _detect_scene_cuts(video_path)
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
        per_second_descriptions = []
        scene_segments = []
        justification_timeline = []

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

        dense_captions = []
        if DENSE_INTERVAL > 0:
            dense_times = []
            t = 0.0
            while t <= duration:
                dense_times.append(t)
                t += DENSE_INTERVAL
            dense_captions = _caption_frames_at_times(frame_files, dense_times, known_entities)

        scene_captions = []
        if scene_cuts:
            scene_marks = sorted(set([0.0] + scene_cuts))
            scene_captions = _caption_frames_at_times(frame_files, scene_marks, known_entities)

        if PER_SECOND_FPS > 0 and frame_files:
            step = 1.0 / PER_SECOND_FPS
            per_second_times = []
            t = 0.0
            while t <= duration:
                per_second_times.append(round(t, 3))
                t += step
            per_second_descriptions = _describe_frames_at_times(frame_files, per_second_times, known_entities)

        if frame_files:
            scene_marks = sorted(set([0.0] + scene_cuts + [duration]))
            frame_count = len(frame_files)
            segment_requests: list[tuple[float, float, list[Path]]] = []

            for idx in range(len(scene_marks) - 1):
                t_start = float(scene_marks[idx])
                t_end = float(scene_marks[idx + 1])
                if t_end <= t_start:
                    continue
                sample_times = _sample_segment_times(t_start, t_end, SCENE_SAMPLE_COUNT)
                frame_paths = []
                for t in sample_times:
                    frame_idx = _frame_index_for_timestamp(t, frame_count)
                    frame_paths.append(frame_files[frame_idx])
                segment_requests.append((t_start, t_end, frame_paths))

            def _run_segment(request: tuple[float, float, list[Path]]) -> dict:
                t_start, t_end, frame_paths = request
                payload = _describe_scene_segment(frame_paths, known_entities, t_start, t_end)
                return {
                    "t_start": round(t_start, 3),
                    "t_end": round(t_end, 3),
                    **payload,
                }

            scene_segments = _parallel_map(segment_requests, _run_segment, VLM_CONCURRENCY)
            for idx, segment in enumerate(scene_segments):
                segment["id"] = idx

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

        justification_timeline = _build_justification_timeline(
            per_second_descriptions,
            scene_segments,
            audio_segments,
            duration,
        )

        result = {
            "fps": FPS,
            "duration": round(duration, 3),
            "scene_cuts": scene_cuts,
            "captions": captions,
            "events": events,
            "dense_captions": dense_captions,
            "scene_captions": scene_captions,
            "per_second_descriptions": per_second_descriptions,
            "scene_segments": scene_segments,
            "justification_timeline": justification_timeline,
            "background_updates": background_updates,
            "audio_segments": audio_segments,
        }

        output_path.write_text(json.dumps(result, indent=2))
        return result
