import os
import platform
import subprocess
import tempfile
from pathlib import Path
from functools import lru_cache


def _run_ffmpeg(args: list[str]) -> None:
    subprocess.run(args, check=True)


def _normalize_flag(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if value == "" or value.lower() in {"0", "false", "none", "off"}:
        return None
    return value


@lru_cache(maxsize=1)
def _ffmpeg_filters() -> str:
    try:
        result = subprocess.run(
            ["ffmpeg", "-filters"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout
    except Exception:
        return ""


def _has_filter(name: str) -> bool:
    return f" {name} " in _ffmpeg_filters() or f"\n{name} " in _ffmpeg_filters()


HWACCEL = _normalize_flag(os.getenv("VIDEO_HWACCEL"))
ENCODER = _normalize_flag(os.getenv("VIDEO_ENCODER"))
PRESET = _normalize_flag(os.getenv("VIDEO_PRESET", "veryfast"))
CRF = _normalize_flag(os.getenv("VIDEO_CRF", "23"))
THREADS = _normalize_flag(os.getenv("VIDEO_THREADS"))
FASTSTART = os.getenv("VIDEO_FASTSTART", "1") != "0"

if HWACCEL is None and platform.system().lower() == "darwin":
    HWACCEL = "videotoolbox"

if ENCODER is None:
    ENCODER = "h264_videotoolbox" if HWACCEL == "videotoolbox" else "libx264"


def _base_args(input_path: str) -> list[str]:
    args = ["ffmpeg", "-y"]
    if HWACCEL:
        args += ["-hwaccel", HWACCEL]
    args += ["-i", input_path]
    return args


def _encode_args() -> list[str]:
    args = ["-c:v", ENCODER, "-c:a", "aac"]
    if ENCODER == "libx264":
        if PRESET:
            args += ["-preset", PRESET]
        if CRF:
            args += ["-crf", str(CRF)]
    if THREADS:
        args += ["-threads", str(THREADS)]
    if FASTSTART:
        args += ["-movflags", "+faststart"]
    return args


def _atempo_filter(factor: float) -> str:
    if factor <= 0:
        raise ValueError("Speed factor must be positive")

    parts = []
    remaining = factor
    while remaining > 2.0:
        parts.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        parts.append(0.5)
        remaining /= 0.5
    parts.append(remaining)
    return ",".join([f"atempo={p:.4f}" for p in parts])


def _escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def change_speed_video(input_path: str, output_path: str, factor: float = 1.05) -> None:
    if not isinstance(factor, (int, float)) or factor <= 0:
        raise ValueError("Speed factor must be a positive number")

    args = [
        *_base_args(input_path),
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-filter:v",
        f"setpts=PTS/{factor}",
        "-filter:a",
        _atempo_filter(float(factor)),
        *_encode_args(),
        output_path,
    ]

    _run_ffmpeg(args)


def speed_up_video(input_path: str, output_path: str, factor: float = 1.05) -> None:
    change_speed_video(input_path, output_path, factor)


def color_grade_video(
    input_path: str,
    output_path: str,
    contrast: float = 1.1,
    brightness: float = 0.03,
    saturation: float = 1.15,
) -> None:
    filter_expr = f"eq=contrast={contrast}:brightness={brightness}:saturation={saturation}"
    args = [
        *_base_args(input_path),
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-vf",
        filter_expr,
        *_encode_args(),
        output_path,
    ]
    _run_ffmpeg(args)


def add_film_grain_video(input_path: str, output_path: str, strength: float = 15.0) -> None:
    noise = max(1.0, float(strength))
    filter_expr = f"noise=alls={noise}:allf=t+u"
    args = [
        *_base_args(input_path),
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-vf",
        filter_expr,
        *_encode_args(),
        output_path,
    ]
    _run_ffmpeg(args)


def blur_backdrop_video(
    input_path: str,
    output_path: str,
    scale: float = 0.85,
    blur: float = 20.0,
) -> None:
    scale = max(0.2, min(float(scale), 1.0))
    blur = max(1.0, float(blur))
    filter_expr = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]boxblur={blur}:{max(1.0, blur / 2)}[bg];"
        f"[fg]scale=iw*{scale}:ih*{scale}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )
    args = [
        *_base_args(input_path),
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-filter_complex",
        filter_expr,
        *_encode_args(),
        output_path,
    ]
    _run_ffmpeg(args)


def reframe_vertical_video(
    input_path: str,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    blur: float = 28.0,
) -> None:
    blur = max(1.0, float(blur))
    filter_expr = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"boxblur={blur}:{max(1.0, blur / 2)}[bg];"
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )
    args = [
        *_base_args(input_path),
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-filter_complex",
        filter_expr,
        *_encode_args(),
        output_path,
    ]
    _run_ffmpeg(args)


def add_text_overlay_video(
    input_path: str,
    output_path: str,
    text: str,
    x: int = 24,
    y: int = 24,
    font_size: int = 36,
    color: str = "white",
    box: int = 1,
    box_color: str = "black@0.5",
    font_path: str | None = None,
    start: float | None = None,
    end: float | None = None,
) -> None:
    if not _has_filter("drawtext"):
        raise RuntimeError("ffmpeg build missing drawtext filter. Install ffmpeg with libfreetype.")
    safe_text = _escape_drawtext(text)
    drawtext = (
        f"drawtext=text='{safe_text}':x={x}:y={y}:fontsize={font_size}:"
        f"fontcolor={color}:box={box}:boxcolor={box_color}"
    )
    if font_path:
        drawtext = f"drawtext=fontfile={font_path}:text='{safe_text}':x={x}:y={y}:fontsize={font_size}:" \
                   f"fontcolor={color}:box={box}:boxcolor={box_color}"
    if start is not None or end is not None:
        start_time = 0.0 if start is None else float(start)
        end_time = 10_000.0 if end is None else float(end)
        drawtext += f":enable='between(t,{start_time},{end_time})'"

    args = [
        *_base_args(input_path),
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-vf",
        drawtext,
        *_encode_args(),
        output_path,
    ]
    _run_ffmpeg(args)


def redact_region_video(
    input_path: str,
    output_path: str,
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    args = [
        *_base_args(input_path),
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-vf",
        f"delogo=x={x}:y={y}:w={w}:h={h}",
        *_encode_args(),
        output_path,
    ]
    _run_ffmpeg(args)


def replace_text_region_video(
    input_path: str,
    output_path: str,
    x: int,
    y: int,
    w: int,
    h: int,
    text: str,
    font_size: int = 32,
    color: str = "white",
    box_color: str = "black@0.6",
    font_path: str | None = None,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "redacted.mp4"
        redact_region_video(input_path, str(tmp_path), x, y, w, h)
        add_text_overlay_video(
            str(tmp_path),
            output_path,
            text=text,
            x=x,
            y=y,
            font_size=font_size,
            color=color,
            box=1,
            box_color=box_color,
            font_path=font_path,
        )


def trim_video(input_path: str, output_path: str, start: float = 0.0, duration: float = 6.0) -> None:
    if start < 0 or duration <= 0:
        raise ValueError("Start must be >= 0 and duration must be > 0")

    args = ["ffmpeg", "-y"]
    if HWACCEL:
        args += ["-hwaccel", HWACCEL]
    args += [
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-i",
        input_path,
        "-map",
        "0:v",
        "-map",
        "0:a?",
        *_encode_args(),
        output_path,
    ]
    _run_ffmpeg(args)


def reverse_video(input_path: str, output_path: str) -> None:
    args = [
        *_base_args(input_path),
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-vf",
        "reverse",
        "-af",
        "areverse",
        *_encode_args(),
        output_path,
    ]
    _run_ffmpeg(args)


def apply_combo(input_path: str, output_path: str, combo_name: str) -> None:
    combos = {
        "vertical_focus": [
            ("reframe_vertical", {"width": 1080, "height": 1920, "blur": 28}),
            ("color_grade", {"contrast": 1.08, "brightness": 0.02, "saturation": 1.05}),
        ],
        "hook_caption": [
            ("trim", {"start": 0.0, "duration": 7.0}),
            ("text_overlay", {"text": "WAIT FOR IT", "x": 32, "y": 32, "font_size": 40, "start": 0, "end": 2.5}),
        ],
        "cutdown_fast": [
            ("trim", {"start": 0.0, "duration": 10.0}),
            ("speed", {"factor": 1.08}),
        ],
        "focus_backdrop": [
            ("backdrop", {"scale": 0.82, "blur": 26}),
            ("color_grade", {"contrast": 1.06, "brightness": 0.01, "saturation": 1.02}),
        ],
        "cinematic_grain": [
            ("color_grade", {"contrast": 1.08, "brightness": 0.01, "saturation": 0.95}),
            ("grain", {"strength": 14}),
        ],
    }

    if combo_name not in combos:
        raise ValueError(f"Unknown combo: {combo_name}")

    steps = combos[combo_name]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        current_input = input_path

        for index, (step, params) in enumerate(steps):
            is_last = index == len(steps) - 1
            step_output = output_path if is_last else str(tmp_dir_path / f"step-{index}.mp4")

            if step == "speed":
                change_speed_video(current_input, step_output, **params)
            elif step == "color_grade":
                color_grade_video(current_input, step_output, **params)
            elif step == "grain":
                add_film_grain_video(current_input, step_output, **params)
            elif step == "trim":
                trim_video(current_input, step_output, **params)
            elif step == "reverse":
                reverse_video(current_input, step_output)
            elif step == "text_overlay":
                add_text_overlay_video(current_input, step_output, **params)
            elif step == "backdrop":
                blur_backdrop_video(current_input, step_output, **params)
            elif step == "reframe_vertical":
                reframe_vertical_video(current_input, step_output, **params)
            else:
                raise ValueError(f"Unknown step: {step}")

            current_input = step_output
