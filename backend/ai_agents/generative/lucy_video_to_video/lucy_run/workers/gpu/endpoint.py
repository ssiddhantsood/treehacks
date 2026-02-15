from runpod_flash import LiveServerless, remote

gpu_config = LiveServerless(
    name="lucy_edit_dev_gpu",
    gpus=["NVIDIA A100-SXM4-80GB"],
    workersMin=1,
    workersMax=2,
    idleTimeout=10,
)

@remote(
    resource_config=gpu_config,
    dependencies=[
        "diffusers>=0.35.1",
        "torch",
        "transformers",
        "accelerate",
        "ftfy",
        "regex",
        "Pillow",
        "imageio[ffmpeg]",
        "sentencepiece",
    ],
    system_dependencies=["ffmpeg"],
)
async def run_lucy_edit(input_data: dict) -> dict:
    import base64
    import inspect
    import os
    import time
    import traceback
    from datetime import datetime

    import numpy as np
    import torch
    from PIL import Image
    from diffusers import AutoencoderKLWan, LucyEditPipeline
    from diffusers.utils import export_to_video, load_video

    # Cache pipeline in function globals so warm workers can reuse loaded weights.
    fn_globals = run_lucy_edit.__globals__

    def get_pipeline(model_id: str):
        cached_pipe = fn_globals.get("_PIPE")
        cached_model = fn_globals.get("_PIPE_MODEL")
        if cached_pipe is not None and cached_model == model_id:
            return cached_pipe

        vae = AutoencoderKLWan.from_pretrained(
            model_id,
            subfolder="vae",
            torch_dtype=torch.float32,
        )
        pipe = LucyEditPipeline.from_pretrained(
            model_id,
            vae=vae,
            torch_dtype=torch.bfloat16,
        )
        pipe.to("cuda")
        fn_globals["_PIPE"] = pipe
        fn_globals["_PIPE_MODEL"] = model_id
        return pipe

    prompt = input_data.get("prompt", "")
    video_url = input_data.get("video_url", "")
    negative_prompt = input_data.get("negative_prompt", "")
    num_frames = int(input_data.get("num_frames", 81))
    height = int(input_data.get("height", 480))
    width = int(input_data.get("width", 832))
    guidance_scale = float(input_data.get("guidance_scale", 5.0))
    strength = float(input_data.get("strength", 0.85))
    num_inference_steps = int(input_data.get("num_inference_steps", 40))
    seed = int(input_data.get("seed", 42))
    fps = int(input_data.get("fps", 24))
    model_id = input_data.get("model_id", "decart-ai/Lucy-Edit-Dev")

    if not prompt:
        return {"status": "error", "error": "'prompt' is required"}
    if not video_url:
        return {"status": "error", "error": "'video_url' is required"}

    try:
        def to_pil_rgb(frame):
            if isinstance(frame, Image.Image):
                return frame.convert("RGB")
            if isinstance(frame, np.ndarray):
                arr = frame
                if arr.dtype != np.uint8:
                    # Many video loaders return float frames in [0, 1].
                    if np.issubdtype(arr.dtype, np.floating):
                        arr = np.clip(arr, 0.0, 1.0) * 255.0
                    arr = np.clip(arr, 0, 255).astype(np.uint8)
                if arr.ndim == 2:
                    arr = np.stack([arr, arr, arr], axis=-1)
                if arr.shape[-1] == 4:
                    arr = arr[..., :3]
                return Image.fromarray(arr).convert("RGB")
            raise TypeError(f"Unsupported frame type: {type(frame)}")

        def to_np_rgb(frame):
            if isinstance(frame, np.ndarray):
                arr = frame
                if arr.dtype != np.uint8:
                    if np.issubdtype(arr.dtype, np.floating):
                        arr = np.clip(arr, 0.0, 1.0) * 255.0
                    arr = np.clip(arr, 0, 255).astype(np.uint8)
                if arr.ndim == 2:
                    arr = np.stack([arr, arr, arr], axis=-1)
                if arr.shape[-1] == 4:
                    arr = arr[..., :3]
                return arr
            if isinstance(frame, Image.Image):
                return np.array(frame.convert("RGB"))
            raise TypeError(f"Unsupported frame type: {type(frame)}")

        def convert_video(video):
            video = video[:num_frames]
            return [to_pil_rgb(frame).resize((width, height)) for frame in video]

        source_video = load_video(video_url, convert_method=convert_video)
        if not source_video:
            return {"status": "error", "error": "Input video could not be loaded"}

        frame_count = min(num_frames, len(source_video))
        resized = [to_pil_rgb(source_video[i]).resize((width, height)) for i in range(frame_count)]

        pipe = get_pipeline(model_id)
        pipe_sig = inspect.signature(pipe.__call__)
        supports_strength = "strength" in pipe_sig.parameters
        generator = torch.Generator(device="cuda").manual_seed(seed)

        call_kwargs = {
            "prompt": prompt,
            "video": resized,
            "negative_prompt": negative_prompt,
            "height": height,
            "width": width,
            "num_frames": frame_count,
            "guidance_scale": guidance_scale,
            "num_inference_steps": num_inference_steps,
            "generator": generator,
        }
        if supports_strength:
            call_kwargs["strength"] = strength

        def sampled_diff(input_frames, output_frames, count):
            sample_indices_local = sorted(set([0, count // 2, max(count - 1, 0)]))
            sampled_local = []
            for idx in sample_indices_local:
                in_np = to_np_rgb(input_frames[idx]).astype(np.float32)
                out_np = to_np_rgb(output_frames[idx]).astype(np.float32)
                mean_abs_diff = float(np.mean(np.abs(in_np - out_np)))
                sampled_local.append(
                    {"frame_index": idx, "mean_abs_pixel_diff": round(mean_abs_diff, 4)}
                )
            max_local = max((d["mean_abs_pixel_diff"] for d in sampled_local), default=0.0)
            return sampled_local, max_local

        t0 = time.time()
        result = pipe(**call_kwargs).frames[0]
        inference_seconds = round(time.time() - t0, 3)
        sampled_diffs, max_sampled_diff = sampled_diff(resized, result, frame_count)

        output_dir = "/tmp/lucy_outputs"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(
            output_dir,
            f"lucy_edit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
        )

        export_to_video(result, output_path, fps=fps)
        with open(output_path, "rb") as f:
            video_base64 = base64.b64encode(f.read()).decode("utf-8")

        return {
            "status": "success",
            "model_id": model_id,
            "prompt": prompt,
            "video_url": video_url,
            "output_path": output_path,
            "video_base64": video_base64,
            "num_frames": frame_count,
            "width": width,
            "height": height,
            "fps": fps,
            "guidance_scale": guidance_scale,
            "strength": strength,
            "num_inference_steps": num_inference_steps,
            "seed": seed,
            "transform_diagnostics": {
                "sampled_frame_diffs": sampled_diffs,
                "max_sampled_mean_abs_pixel_diff": max_sampled_diff,
                "output_changed_vs_input": max_sampled_diff > 0.0,
            },
            "execution_diagnostics": {
                "pipeline_class": pipe.__class__.__name__,
                "supports_strength": supports_strength,
                "inference_seconds": inference_seconds,
                "call_kwargs_used": sorted(call_kwargs.keys()),
            },
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now().isoformat(),
        }
    finally:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
