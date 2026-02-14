import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils import ffprobe, run_cmd, ensure_parent


def _load_rvm():
    repo_path = os.getenv("RVM_REPO")
    checkpoint = os.getenv("RVM_CHECKPOINT")
    if not repo_path or not checkpoint:
        raise RuntimeError("Set RVM_REPO and RVM_CHECKPOINT to use background replacement.")

    sys.path.insert(0, repo_path)
    try:
        from model import MattingNetwork
        from inference import convert_video
    except ImportError as exc:
        raise RuntimeError("Could not import RVM modules. Check RVM_REPO path.") from exc

    model_type = os.getenv("RVM_MODEL", "mobilenetv3")
    if model_type == "resnet50":
        model = MattingNetwork("resnet50")
    else:
        model = MattingNetwork("mobilenetv3")

    model.load_state_dict(torch.load(checkpoint, map_location="cpu"))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device).eval()
    return model, convert_video


def _generate_background(prompt: str, width: int, height: int, seed: int | None) -> Image.Image:
    from diffusers import StableDiffusionXLPipeline

    model_id = os.getenv("BACKGROUND_MODEL", "stabilityai/sdxl-turbo")
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    pipe = StableDiffusionXLPipeline.from_pretrained(model_id, torch_dtype=dtype)
    pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")

    generator = None
    if seed is not None:
        generator = torch.Generator(device=pipe.device).manual_seed(seed)

    result = pipe(prompt=prompt, width=width, height=height, generator=generator, num_inference_steps=4)
    return result.images[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Background replacement pipeline (GPU)")
    parser.add_argument("--job", required=True, help="Path to job json")
    args = parser.parse_args()

    job_path = Path(args.job)
    job = json.loads(job_path.read_text())

    if job.get("job_type") != "background_replace":
        raise RuntimeError("Job type must be background_replace")

    input_video = job["inputVideo"]
    output_video = job["outputVideo"]
    prompt = job.get("prompt", "")
    background_image = job.get("backgroundImage")
    seed = job.get("seed")

    ensure_parent(Path(output_video))

    info = ffprobe(input_video)
    width = info["width"]
    height = info["height"]
    duration = info["duration"]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        fgr_path = tmp_path / "fgr.mp4"
        pha_path = tmp_path / "pha.mp4"
        bg_path = tmp_path / "background.png"

        model, convert_video = _load_rvm()
        convert_video(
            model,
            input_video,
            str(fgr_path),
            str(pha_path),
            device="cuda" if torch.cuda.is_available() else "cpu",
            downsample_ratio=None,
            seq_chunk=12,
            progress=True,
        )

        if background_image:
            Image.open(background_image).convert("RGB").resize((width, height)).save(bg_path)
        else:
            if not prompt:
                raise RuntimeError("Provide prompt or backgroundImage")
            bg = _generate_background(prompt, width, height, seed)
            bg.save(bg_path)

        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-t",
            str(duration),
            "-i",
            str(bg_path),
            "-i",
            str(fgr_path),
            "-i",
            str(pha_path),
            "-i",
            input_video,
            "-filter_complex",
            f"[1:v][2:v]alphamerge[fg];[0:v]scale={width}:{height}[bg];[bg][fg]overlay=0:0:format=auto[v]",
            "-map",
            "[v]",
            "-map",
            "3:a?",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            output_video,
        ]
        run_cmd(cmd)

    print("Background replacement complete:", output_video)


if __name__ == "__main__":
    main()
