import os
import platform
import subprocess
import tempfile
from pathlib import Path
from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageFont


def _run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr or "(no stderr)"
        # Log full stderr for server-side debugging
        print(f"[ffmpeg] FAILED (exit {result.returncode})")
        print(f"[ffmpeg] cmd: {' '.join(args)}")
        print(f"[ffmpeg] stderr:\n{stderr[-2000:]}")
        raise subprocess.CalledProcessError(
            result.returncode,
            args,
            output=result.stdout,
            stderr=result.stderr,
        )


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


@lru_cache(maxsize=1)
def _ffmpeg_encoders() -> str:
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout
    except Exception:
        return ""


def _has_encoder(name: str) -> bool:
    return name in _ffmpeg_encoders()


def _has_filter(name: str) -> bool:
    return f" {name} " in _ffmpeg_filters() or f"\n{name} " in _ffmpeg_filters()


def _detect_best_encoder() -> str:
    """Auto-detect the best available H.264 encoder."""
    # Prefer libx264 (best quality/compat), fall back through alternatives
    for candidate in ("libx264", "libopenh264", "libx264rgb", "h264_v4l2m2m"):
        if _has_encoder(candidate):
            return candidate
    # If no H.264 encoder found, try mpeg4 as last resort
    if _has_encoder("mpeg4"):
        return "mpeg4"
    # Absolute fallback
    return "libx264"


_RAW_HWACCEL = os.getenv("VIDEO_HWACCEL")
HWACCEL = _normalize_flag(_RAW_HWACCEL)
ENCODER = _normalize_flag(os.getenv("VIDEO_ENCODER"))
PRESET = _normalize_flag(os.getenv("VIDEO_PRESET", "veryfast"))
CRF = _normalize_flag(os.getenv("VIDEO_CRF", "23"))
THREADS = _normalize_flag(os.getenv("VIDEO_THREADS"))
FASTSTART = os.getenv("VIDEO_FASTSTART", "1") != "0"

if HWACCEL is None and _RAW_HWACCEL is None and platform.system().lower() == "darwin":
    HWACCEL = "videotoolbox"

if ENCODER is None:
    if HWACCEL == "videotoolbox":
        ENCODER = "h264_videotoolbox"
    else:
        ENCODER = _detect_best_encoder()

print(f"[video] Encoder: {ENCODER}, HWACCEL: {HWACCEL}, Preset: {PRESET}")


def _base_args(input_path: str) -> list[str]:
    args = ["ffmpeg", "-y"]
    if HWACCEL:
        args += ["-hwaccel", HWACCEL]
    args += ["-i", input_path]
    return args


def _encode_args() -> list[str]:
    args = ["-c:v", ENCODER, "-c:a", "aac"]
    if ENCODER in ("libx264", "libx264rgb"):
        if PRESET:
            args += ["-preset", PRESET]
        if CRF:
            args += ["-crf", str(CRF)]
    elif ENCODER == "libopenh264":
        # libopenh264 doesn't support crf, use -b:v instead
        args += ["-b:v", "2M"]
    elif ENCODER == "mpeg4":
        # mpeg4 uses -q:v (1-31, lower=better)
        args += ["-q:v", "5"]
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
    """Escape text for FFmpeg drawtext filter values."""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _escape_drawtext_path(path: str) -> str:
    """Escape a file path for FFmpeg drawtext fontfile= value.

    On Windows the drive-letter colon must be escaped *and* the whole path
    must be single-quoted so FFmpeg's filter parser treats it as one token.
    """
    cleaned = path.replace("\\", "/")
    escaped = cleaned.replace(":", "\\:")
    return f"'{escaped}'"


def _default_font_path() -> str | None:
    """Return a usable font file path, especially needed on Windows where fontconfig is broken."""
    if platform.system().lower() == "windows":
        candidates = [
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f)
            for f in ("arial.ttf", "Arial.ttf", "segoeui.ttf", "calibri.ttf")
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    return None


def _font_candidates() -> list[str]:
    return [
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Helvetica.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]


def _load_font(font_path: str | None, font_size: int) -> ImageFont.ImageFont:
    if font_path and os.path.isfile(font_path):
        try:
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            pass
    for candidate in _font_candidates():
        if os.path.isfile(candidate):
            try:
                return ImageFont.truetype(candidate, font_size)
            except Exception:
                continue
    try:
        return ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        return ImageFont.load_default()


def _parse_color(value: str, default_alpha: float = 1.0) -> tuple[int, int, int, int]:
    text = (value or "").strip()
    alpha = default_alpha
    if "@" in text:
        base, _, tail = text.partition("@")
        text = base.strip()
        try:
            alpha = float(tail.strip())
        except ValueError:
            alpha = default_alpha
    if not text:
        text = "white"
    try:
        rgb = ImageColor.getrgb(text)
    except Exception:
        rgb = (255, 255, 255)
    a = max(0, min(255, int(round(255 * alpha))))
    return (rgb[0], rgb[1], rgb[2], a)


def _render_text_overlay(
    text: str,
    font_size: int,
    color: str,
    box: int,
    box_color: str,
    font_path: str | None = None,
) -> Image.Image:
    font = _load_font(font_path, font_size)
    dummy = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])
    except Exception:
        text_w, text_h = draw.textsize(text, font=font)
    pad = max(6, int(font_size * 0.28))
    img_w = text_w + pad * 2
    img_h = text_h + pad * 2
    image = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if box:
        box_rgba = _parse_color(box_color, default_alpha=0.6)
        draw.rectangle([0, 0, img_w, img_h], fill=box_rgba)
    text_rgba = _parse_color(color, default_alpha=1.0)
    draw.text((pad, pad), text, font=font, fill=text_rgba)
    return image


def _overlay_image_on_video(
    input_path: str,
    output_path: str,
    overlay_path: str,
    x: int,
    y: int,
    start: float | None,
    end: float | None,
) -> None:
    filter_expr = f"[0:v][1:v]overlay={x}:{y}:shortest=1:eof_action=pass"
    if start is not None or end is not None:
        start_time = 0.0 if start is None else float(start)
        end_time = 10_000.0 if end is None else float(end)
        filter_expr += f":enable='between(t,{start_time},{end_time})'"
    filter_expr += "[v]"

    args = ["ffmpeg", "-y"]
    if HWACCEL:
        args += ["-hwaccel", HWACCEL]
    args += [
        "-i",
        input_path,
        "-loop",
        "1",
        "-i",
        overlay_path,
        "-filter_complex",
        filter_expr,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-shortest",
        *_encode_args(),
        output_path,
    ]
    _run_ffmpeg(args)


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
        with tempfile.TemporaryDirectory() as tmp_dir:
            overlay_path = Path(tmp_dir) / "overlay.png"
            image = _render_text_overlay(
                text=text,
                font_size=font_size,
                color=color,
                box=box,
                box_color=box_color,
                font_path=font_path or _default_font_path(),
            )
            image.save(overlay_path)
            _overlay_image_on_video(
                input_path=input_path,
                output_path=output_path,
                overlay_path=str(overlay_path),
                x=x,
                y=y,
                start=start,
                end=end,
            )
        return

    # Auto-resolve font on Windows where fontconfig is broken
    resolved_font = font_path or _default_font_path()

    safe_text = _escape_drawtext(text)
    if resolved_font:
        safe_font = _escape_drawtext_path(resolved_font)
        drawtext = (
            f"drawtext=fontfile={safe_font}:text='{safe_text}':"
            f"x={x}:y={y}:fontsize={font_size}:"
            f"fontcolor={color}:box={box}:boxcolor={box_color}"
        )
    else:
        drawtext = (
            f"drawtext=text='{safe_text}':x={x}:y={y}:fontsize={font_size}:"
            f"fontcolor={color}:box={box}:boxcolor={box_color}"
        )
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


def apply_combo(
    input_path: str,
    output_path: str,
    combo_name: str,
    overlay_text: str | None = None,
    overlay_start: float | None = None,
    overlay_end: float | None = None,
    overlay_x: int = 32,
    overlay_y: int = 32,
    overlay_font_size: int = 40,
) -> None:
    text_value = (overlay_text or "WAIT FOR IT").strip() or "WAIT FOR IT"
    start_value = 0.0 if overlay_start is None else float(overlay_start)
    end_value = 2.5 if overlay_end is None else float(overlay_end)
    if end_value <= start_value:
        end_value = start_value + 1.8
    x_value = int(overlay_x)
    y_value = int(overlay_y)
    font_value = int(overlay_font_size)

    combos = {
        "vertical_focus": [
            ("reframe_vertical", {"width": 1080, "height": 1920, "blur": 28}),
            ("color_grade", {"contrast": 1.08, "brightness": 0.02, "saturation": 1.05}),
        ],
        "hook_caption": [
            ("trim", {"start": 0.0, "duration": 7.0}),
            (
                "text_overlay",
                {
                    "text": text_value,
                    "x": x_value,
                    "y": y_value,
                    "font_size": font_value,
                    "start": start_value,
                    "end": end_value,
                },
            ),
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
