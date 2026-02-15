# Lucy Run

Run `decart-ai/Lucy-Edit-Dev` as a Runpod Flash GPU worker.

## Setup

```bash
cd lucy_run
pip install -r requirements.txt
export RUNPOD_API_KEY=your_key_here
flash run
```

Server default: `http://localhost:8000`

## Test

```bash
curl -X POST http://localhost:8000/gpu/edit \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://d2drjpuinn46lb.cloudfront.net/painter_original_edit.mp4",
    "prompt": "Change the apron and blouse to a classic clown costume: satin polka-dot jumpsuit in bright primary colors, ruffled white collar, oversized pom-pom buttons, white gloves, oversized red shoes, red foam nose; soft window light from left, eye-level medium shot, natural folds and fabric highlights.",
    "negative_prompt": "",
    "num_frames": 81,
    "height": 480,
    "width": 832,
    "guidance_scale": 7.0,
    "strength": 0.85,
    "num_inference_steps": 40,
    "seed": 42,
    "fps": 24
  }'
```

Response includes `local_output_path`, `transform_diagnostics`, and `execution_diagnostics` to verify the model call actually ran.

## Notes

- GPU resource is currently set to `GpuGroup.AMPERE_80` with `workersMax=1`.
- If deployment fails due to quota/availability, change `gpus` in `workers/gpu/endpoint.py`.
