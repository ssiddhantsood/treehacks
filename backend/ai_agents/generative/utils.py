import json
import subprocess
from pathlib import Path


def run_cmd(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffprobe(video_path: str) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        video_path,
    ]
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    payload = json.loads(result.stdout)
    stream = payload.get("streams", [{}])[0]

    def _parse_fps(value: str | None) -> float:
        if not value:
            return 0.0
        if "/" in value:
            num, den = value.split("/")
            try:
                return float(num) / float(den)
            except ZeroDivisionError:
                return 0.0
        return float(value)

    fps = _parse_fps(stream.get("avg_frame_rate")) or _parse_fps(stream.get("r_frame_rate"))

    return {
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "fps": fps,
        "duration": float(payload.get("format", {}).get("duration", 0.0)),
    }


def extract_frames(video_path: str, out_dir: Path, fps: float | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", video_path]
    if fps:
        cmd += ["-vf", f"fps={fps}"]
    cmd += [str(out_dir / "%06d.png")]
    run_cmd(cmd)


def build_video_from_frames(
    frames_dir: Path,
    fps: float,
    output_path: str,
    audio_source: str | None = None,
) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "%06d.png"),
    ]
    if audio_source:
        cmd += ["-i", audio_source]
    cmd += [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]
    run_cmd(cmd)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
