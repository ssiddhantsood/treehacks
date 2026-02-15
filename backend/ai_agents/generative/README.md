# Generative Video Tools (GPU)

This folder is for **heavy GPU workflows** (RunPod or any CUDA machine).
Each workflow is intended to be triggered via an AI agent that emits a job
spec, then executed by a script on the GPU box.

## Workflows & Methodology

### 1) Background Replacement ("green screen without green")
Goal: replace the background while preserving the subject.

Implementation (GPU script):
- Uses **Robust Video Matting (RVM)** to extract foreground + alpha.
- Generates a background with **SDXL Turbo** (or uses `backgroundImage`).
- Composites foreground over the generated background and re-attaches audio.

### 2) Object Erasing
Goal: remove a visible object across time.

Implementation (GPU script):
- Detects the object with **GroundingDINO** from a text prompt.
- Segments it with **Segment Anything** (SAM).
- Inpaints the masked region using **ProPainter** for video inpainting.

### 3) Word / Text Replacement
Goal: replace on-screen text with new wording.

Implementation (GPU script):
- OCR with **PaddleOCR** (or EasyOCR fallback).
- Inpaint the text region with **Simple LaMa** (image inpainting).
- Render new text with PIL and re-encode video.

## How it works
- The **agent** writes a job spec to `backend/ai_agents/generative/jobs/`.
- Run a script on a GPU box to execute the job.

## Setup (RunPod)
- Install GPU deps from `requirements-gpu.txt`.
- Clone the repos required by each pipeline and set env vars:
  - `RVM_REPO`, `RVM_CHECKPOINT`
  - `GROUNDINGDINO_CONFIG`, `GROUNDINGDINO_WEIGHTS`
  - `SAM_CHECKPOINT`, `SAM_MODEL_TYPE`
  - `PROPAINTER_REPO`
 - Optional: `BACKGROUND_MODEL` (for text-to-image backgrounds).
 - Ensure the repos are importable (e.g. `pip install -e <repo>` or add to `PYTHONPATH`).

## Example job
```json
{
  "job_type": "background_replace",
  "input_video": "/data/input.mp4",
  "output_video": "/data/output.mp4",
  "prompt": "sunset beach with palm trees",
  "subject": "person",
  "seed": 42
}
```

## RunPod usage (example)
1. Sync this repo to your RunPod volume.
2. Run the appropriate script:
   - `python scripts/background_replace.py --job /path/to/job.json`
   - `python scripts/object_erase.py --job /path/to/job.json`
   - `python scripts/text_replace.py --job /path/to/job.json`

The scripts are implemented but expect the repos and checkpoints above to be present.
