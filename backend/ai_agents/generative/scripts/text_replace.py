import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils import build_video_from_frames, extract_frames, ffprobe, ensure_parent


def _load_ocr():
    engine = os.getenv("OCR_ENGINE", "paddle").lower()
    if engine == "easy":
        import easyocr

        reader = easyocr.Reader(["en"], gpu=True)

        def detect(image):
            results = reader.readtext(image)
            return [
                {
                    "box": np.array(r[0], dtype=np.int32),
                    "text": r[1],
                    "score": float(r[2]),
                }
                for r in results
            ]

        return detect

    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_angle_cls=True, lang="en")

    def detect(image):
        result = ocr.ocr(image, cls=True)
        detections = []
        for line in result[0]:
            box, (text, score) = line
            detections.append({"box": np.array(box, dtype=np.int32), "text": text, "score": float(score)})
        return detections

    return detect


def _load_inpainter():
    from simple_lama import SimpleLama

    return SimpleLama()


def _match_boxes(detections, target_text):
    if not target_text:
        return detections
    target_text = target_text.lower().strip()
    matched = []
    for item in detections:
        if target_text in item["text"].lower():
            matched.append(item)
    return matched


def _draw_text(image: Image.Image, box, text, font_path: str | None, font_size: int, color: str):
    draw = ImageDraw.Draw(image)
    if font_path and Path(font_path).exists():
        font = ImageFont.truetype(font_path, font_size)
    else:
        font = ImageFont.load_default()

    if box is None:
        draw.text((16, 16), text, fill=color, font=font)
        return

    x_min = int(np.min(box[:, 0]))
    y_min = int(np.min(box[:, 1]))
    draw.text((x_min, y_min), text, fill=color, font=font)


def main() -> None:
    parser = argparse.ArgumentParser(description="Text replace pipeline (GPU)")
    parser.add_argument("--job", required=True, help="Path to job json")
    args = parser.parse_args()

    job = json.loads(Path(args.job).read_text())
    if job.get("job_type") != "text_replace":
        raise RuntimeError("Job type must be text_replace")

    input_video = job["inputVideo"]
    output_video = job["outputVideo"]
    target_text = job.get("targetText", "")
    new_text = job.get("newText")
    if not new_text:
        raise RuntimeError("newText is required")

    font_path = job.get("fontPath")
    font_size = int(job.get("fontSize", 32))
    color = job.get("color", "white")

    ensure_parent(Path(output_video))

    info = ffprobe(input_video)
    fps = info["fps"] or 24

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        frames_dir = tmp_path / "frames"
        masks_dir = tmp_path / "masks"
        out_frames_dir = tmp_path / "out_frames"

        extract_frames(input_video, frames_dir)
        masks_dir.mkdir(parents=True, exist_ok=True)
        out_frames_dir.mkdir(parents=True, exist_ok=True)

        detect = _load_ocr()
        inpainter = _load_inpainter()

        for frame_path in sorted(frames_dir.glob("*.png")):
            image_bgr = cv2.imread(str(frame_path))
            detections = detect(image_bgr)
            matched = _match_boxes(detections, target_text)

            mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
            box_for_text = None
            for item in matched:
                box = item["box"]
                box_for_text = box
                cv2.fillPoly(mask, [box.astype(np.int32)], 255)

            if np.any(mask > 0):
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                mask_rgb = mask
                result = inpainter(Image.fromarray(image_rgb), Image.fromarray(mask_rgb))
                result_bgr = cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
            else:
                result_bgr = image_bgr

            result_img = Image.fromarray(cv2.cvtColor(result_bgr, cv2.COLOR_BGR2RGB))
            _draw_text(result_img, box_for_text, new_text, font_path, font_size, color)

            out_path = out_frames_dir / frame_path.name
            result_img.save(out_path)

        build_video_from_frames(out_frames_dir, fps=fps, output_path=output_video, audio_source=input_video)

    print("Text replace complete:", output_video)


if __name__ == "__main__":
    main()
