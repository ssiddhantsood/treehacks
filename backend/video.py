import subprocess
import tempfile
from pathlib import Path


def _run_ffmpeg(args: list[str]) -> None:
    subprocess.run(args, check=True)


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


def change_speed_video(input_path: str, output_path: str, factor: float = 1.05) -> None:
    if not isinstance(factor, (int, float)) or factor <= 0:
        raise ValueError("Speed factor must be a positive number")

    args = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-filter:v",
        f"setpts=PTS/{factor}",
        "-filter:a",
        _atempo_filter(float(factor)),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
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
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-vf",
        filter_expr,
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        output_path,
    ]
    _run_ffmpeg(args)


def trim_video(input_path: str, output_path: str, start: float = 0.0, duration: float = 6.0) -> None:
    if start < 0 or duration <= 0:
        raise ValueError("Start must be >= 0 and duration must be > 0")

    args = [
        "ffmpeg",
        "-y",
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
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        output_path,
    ]
    _run_ffmpeg(args)


def reverse_video(input_path: str, output_path: str) -> None:
    args = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-map",
        "0:v",
        "-map",
        "0:a?",
        "-vf",
        "reverse",
        "-af",
        "areverse",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        output_path,
    ]
    _run_ffmpeg(args)


def apply_combo(input_path: str, output_path: str, combo_name: str) -> None:
    combos = {
        "warm_boost": [
            ("color_grade", {"contrast": 1.12, "brightness": 0.04, "saturation": 1.25}),
            ("speed", {"factor": 1.08}),
        ],
        "cool_slow": [
            ("color_grade", {"contrast": 1.05, "brightness": -0.02, "saturation": 0.9}),
            ("speed", {"factor": 0.95}),
        ],
        "punchy_trim": [
            ("trim", {"start": 0.0, "duration": 8.0}),
            ("color_grade", {"contrast": 1.15, "brightness": 0.02, "saturation": 1.1}),
        ],
        "reverse_pop": [
            ("reverse", {}),
            ("speed", {"factor": 1.05}),
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
            elif step == "trim":
                trim_video(current_input, step_output, **params)
            elif step == "reverse":
                reverse_video(current_input, step_output)
            else:
                raise ValueError(f"Unknown step: {step}")

            current_input = step_output
