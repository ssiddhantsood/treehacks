import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils import build_video_from_frames, extract_frames, ffprobe, run_cmd, ensure_parent


def _load_grounding_dino():
    config_path = os.getenv("GROUNDINGDINO_CONFIG")
    weights_path = os.getenv("GROUNDINGDINO_WEIGHTS")
    if not config_path or not weights_path:
        raise RuntimeError("Set GROUNDINGDINO_CONFIG and GROUNDINGDINO_WEIGHTS")
    from groundingdino.util.inference import load_model, load_image, predict

    model = load_model(config_path, weights_path)

    def detect(image_path: str, prompt: str, box_threshold: float, text_threshold: float):
        image_source, image = load_image(image_path)
        boxes, logits, phrases = predict(
            model=model,
            image=image,
            caption=prompt,
            box_threshold=box_threshold,
            text_threshold=text_threshold,
        )
        if boxes is None or len(boxes) == 0:
            return None
        h, w, _ = image_source.shape
        boxes = boxes * np.array([w, h, w, h])
        return boxes[0]

    return detect


def _load_sam():
    sam_ckpt = os.getenv("SAM_CHECKPOINT")
    sam_type = os.getenv("SAM_MODEL_TYPE", "vit_h")
    if not sam_ckpt:
        raise RuntimeError("Set SAM_CHECKPOINT for segment-anything")
    from segment_anything import SamPredictor, sam_model_registry

    sam = sam_model_registry[sam_type](checkpoint=sam_ckpt)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    sam = sam.to(device)
    predictor = SamPredictor(sam)

    def predict_mask(image_bgr, box_xyxy):
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        predictor.set_image(image_rgb)
        masks, _, _ = predictor.predict(box=box_xyxy, multimask_output=False)
        return masks[0]

    return predict_mask


def _track_boxes(frames, init_box):
    tracker = cv2.TrackerCSRT_create()
    x1, y1, x2, y2 = init_box
    w, h = x2 - x1, y2 - y1
    tracker.init(frames[0], (x1, y1, w, h))

    boxes = []
    for frame in frames:
        ok, bbox = tracker.update(frame)
        if not ok:
            boxes.append(None)
            continue
        x, y, w, h = bbox
        boxes.append((int(x), int(y), int(x + w), int(y + h)))
    return boxes


def _make_mask_frames(
    frames_dir: Path,
    masks_dir: Path,
    object_prompt: str,
    box_threshold: float,
    text_threshold: float,
) -> None:
    frames = sorted(frames_dir.glob("*.png"))
    if not frames:
        raise RuntimeError("No frames extracted")

    detect = _load_grounding_dino()
    predict_mask = _load_sam()

    first_box = detect(str(frames[0]), object_prompt, box_threshold=box_threshold, text_threshold=text_threshold)
    if first_box is None:
        raise RuntimeError("Object not detected in first frame")

    frames_bgr = [cv2.imread(str(f)) for f in frames]
    boxes = _track_boxes(frames_bgr, first_box.astype(int))

    masks_dir.mkdir(parents=True, exist_ok=True)

    for frame, box, frame_path in zip(frames_bgr, boxes, frames):
        if box is None:
            mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        else:
            mask = predict_mask(frame, np.array(box))
            mask = (mask * 255).astype(np.uint8)
        mask_path = masks_dir / frame_path.name
        cv2.imwrite(str(mask_path), mask)


def _run_propainter(input_video: str, mask_video: str, output_video: str) -> None:
    repo = os.getenv("PROPAINTER_REPO")
    if not repo:
        raise RuntimeError("Set PROPAINTER_REPO for ProPainter inpainting")
    script = Path(repo) / "inference_propainter.py"
    if not script.exists():
        raise RuntimeError("ProPainter inference_propainter.py not found")

    cmd = [
        sys.executable,
        str(script),
        "--video",
        input_video,
        "--mask",
        mask_video,
        "--output",
        output_video,
    ]
    run_cmd(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Object erase pipeline (GPU)")
    parser.add_argument("--job", required=True, help="Path to job json")
    args = parser.parse_args()

    job_path = Path(args.job)
    job = json.loads(job_path.read_text())

    if job.get("job_type") != "object_erase":
        raise RuntimeError("Job type must be object_erase")

    input_video = job["inputVideo"]
    output_video = job["outputVideo"]
    object_prompt = job.get("objectPrompt")
    box_threshold = float(job.get("boxThreshold", 0.35))
    text_threshold = float(job.get("textThreshold", 0.25))
    if not object_prompt:
        raise RuntimeError("objectPrompt is required")

    ensure_parent(Path(output_video))

    info = ffprobe(input_video)
    fps = info["fps"] or 24

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        frames_dir = tmp_path / "frames"
        masks_dir = tmp_path / "masks"
        mask_video = tmp_path / "mask.mp4"

        extract_frames(input_video, frames_dir)
        _make_mask_frames(frames_dir, masks_dir, object_prompt, box_threshold, text_threshold)

        build_video_from_frames(masks_dir, fps=fps, output_path=str(mask_video))
        _run_propainter(input_video, str(mask_video), output_video)

    print("Object erase complete:", output_video)


if __name__ == "__main__":
    main()
