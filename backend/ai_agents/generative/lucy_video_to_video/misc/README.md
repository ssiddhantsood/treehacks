# Miscellaneous Examples

Experimental, specialized, or community-contributed examples that don't fit into the main categories.

## Contents

This directory contains:

- Experimental features
- Community contributions
- Specialized use cases
- Integration examples
- Proof-of-concepts

## Example Format

Examples in this directory may not follow the standard structure. Each example should include its own README explaining:

- What it demonstrates
- Why it's in misc/
- Prerequisites
- How to run it
- Known limitations

## GPU Runner (Lucy Run)

The Lucy GPU runner is a small FastAPI service that forwards edit requests to a Runpod Flash GPU worker and returns the edited video.

How it runs:
- `lucy_run/main.py` starts a FastAPI app and registers the GPU router at `POST /gpu/edit`.
- `lucy_run/workers/gpu/__init__.py` validates the request with `LucyEditRequest`, then calls `run_lucy_edit`.
- `lucy_run/workers/gpu/endpoint.py` defines `run_lucy_edit` as a Runpod Flash `@remote` function with a `LiveServerless` GPU config.
- The remote worker loads the Lucy pipeline, caches it in warm workers, runs inference, writes an MP4 to `/tmp/lucy_outputs`, then returns the video as base64 plus diagnostics.
- The API server decodes the base64 into `lucy_video_to_video/outputs/` and returns `local_output_path` in the response.

Key details:
- GPU config is set in `endpoint.py` with `gpus`, `workersMin`, `workersMax`, and `idleTimeout`.
- Model and inference parameters come from the request body, with sane defaults in `LucyEditRequest`.
- `video_url` must be publicly accessible by the GPU worker.

Endpoints:
- `POST /gpu/edit` to run an edit.
- `GET /health` for a quick health check.

## Contributing

Have an interesting example that doesn't fit the main categories? Contribute it here!

See [../CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

## Note

Examples here are:
- Not part of the guided learning path
- May use experimental features
- May not be continuously tested
- May have different structures
- Should be self-contained

For production-ready patterns, see the numbered categories (01-06).
