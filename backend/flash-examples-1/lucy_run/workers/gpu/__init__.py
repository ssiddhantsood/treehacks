import base64
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .endpoint import run_lucy_edit

gpu_router = APIRouter()


class LucyEditRequest(BaseModel):
    prompt: str = Field(..., description="Editing prompt")
    video_url: str = Field(..., description="Publicly accessible input video URL")
    negative_prompt: str = Field(default="", description="Optional negative prompt")
    num_frames: int = Field(default=81, ge=1, le=161)
    height: int = Field(default=480, ge=128, le=1024)
    width: int = Field(default=832, ge=128, le=1536)
    guidance_scale: float = Field(default=5.0, ge=1.0, le=20.0)
    strength: float = Field(default=0.85, ge=0.0, le=1.0)
    num_inference_steps: int = Field(default=40, ge=1, le=200)
    seed: int = Field(default=42, ge=0)
    fps: int = Field(default=24, ge=1, le=60)
    model_id: str = Field(default="decart-ai/Lucy-Edit-Dev")


@gpu_router.post("/edit")
async def edit_video(request: LucyEditRequest) -> dict:
    payload = {
        "prompt": request.prompt,
        "video_url": request.video_url,
        "negative_prompt": request.negative_prompt,
        "num_frames": request.num_frames,
        "height": request.height,
        "width": request.width,
        "guidance_scale": request.guidance_scale,
        "strength": request.strength,
        "num_inference_steps": request.num_inference_steps,
        "seed": request.seed,
        "fps": request.fps,
        "model_id": request.model_id,
    }
    result = await run_lucy_edit(payload)
    if result.get("status") != "success":
        return result

    video_base64 = result.pop("video_base64", None)
    if not video_base64:
        result["status"] = "error"
        result["error"] = "Remote worker returned success without video payload."
        return result

    outputs_dir = Path(__file__).resolve().parents[2] / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"lucy_edit_{result.get('timestamp', '').replace(':', '-').replace('.', '-')}.mp4"
    if file_name == "lucy_edit_.mp4":
        file_name = "lucy_edit_output.mp4"
    local_output_path = outputs_dir / file_name

    with open(local_output_path, "wb") as f:
        f.write(base64.b64decode(video_base64))

    result["local_output_path"] = str(local_output_path)
    return result
