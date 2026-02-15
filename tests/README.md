# Analysis Test Runner

1. Put a video at `tests/video.mp4`.
2. Run:

```bash
python tests/run_analysis.py
```

Optional flags:

```bash
python tests/run_analysis.py --video /path/to/video.mp4 --out tests/analysis.json
```

This calls the OpenAI-backed analysis pipeline and prints the outputs in readable sections.

## Color grading variants

Generate multiple color-graded versions of `tests/video.mp4`:

```bash
python tests/run_color_grades.py
```

Outputs:
- `tests/graded/video-<preset>.mp4`
- `tests/graded/index.html` (simple gallery)

## Tool smoke test

Run a simple call for each available tool:

```bash
python tests/run_tool_smoke.py
```

Outputs to `tests/tool_smoke/`.
