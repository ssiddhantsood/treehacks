import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ai_agents.agent import _dispatch_tool  # noqa: E402
from ai_agents.generative.agent import (  # noqa: E402
    submit_background_replace,
    submit_object_erase,
    submit_text_replace,
)
from ai_agents.tool_catalog import BASIC_EDIT_TOOLS, GENERATIVE_TOOLS  # noqa: E402


def _print_result(result: dict) -> None:
    name = result.get("name", "")
    status = result.get("status", "")
    detail = result.get("detail", "")
    print(f"- {name}: {status}{' | ' + detail if detail else ''}")


def _run_edit_tools(video_path: Path, out_dir: Path) -> tuple[list[dict], list[str]]:
    available = {tool["function"]["name"] for tool in BASIC_EDIT_TOOLS}
    tasks = [
        ("speed_up_video", {"changeTag": "fast_2", "changeNote": "Smoke test: small lift."}),
        ("change_speed_video", {"changeTag": "slow_2", "changeNote": "Smoke test: small ease."}),
        ("color_grade_video", {"gradeStyle": "neutral_clean", "gradeNote": "Smoke test baseline grade."}),
        ("trim_video", {"start": 0.0, "duration": 2.0}),
        ("apply_combo", {"comboName": "cinematic_grain"}),
        ("add_text_overlay_video", {"text": "SMOKE TEST", "x": 32, "y": 32, "fontSize": 36, "start": 0, "end": 1.5}),
        ("replace_text_region_video", {"x": 20, "y": 20, "w": 240, "h": 80, "text": "TEST", "fontSize": 32}),
        ("blur_backdrop_video", {"scale": 0.85, "blur": 20.0}),
        ("reframe_vertical_video", {"width": 1080, "height": 1920, "blur": 28.0}),
        ("add_film_grain_video", {"strength": 12.0}),
    ]
    covered = {name for name, _ in tasks}
    missing = sorted(available - covered)

    results = []
    for name, args in tasks:
        output_path = out_dir / f"{name}.mp4"
        try:
            _dispatch_tool(name, args, str(video_path), str(output_path))
            results.append({"name": name, "status": "ok", "detail": f"output={output_path}"})
        except RuntimeError as exc:
            message = str(exc)
            if "drawtext" in message.lower():
                results.append({"name": name, "status": "skipped", "detail": message})
            else:
                results.append({"name": name, "status": "error", "detail": message})
        except Exception as exc:
            results.append({"name": name, "status": "error", "detail": str(exc)})

    return results, missing


def _run_generative_tools(video_path: Path, out_dir: Path) -> tuple[list[dict], list[str]]:
    available = {tool["function"]["name"] for tool in GENERATIVE_TOOLS}
    results = []

    tasks = [
        (
            "submit_background_replace",
            submit_background_replace,
            {
                "inputVideo": str(video_path),
                "outputVideo": str(out_dir / "background_replace.mp4"),
                "prompt": "soft sunrise city skyline",
                "subject": "person",
                "seed": 42,
            },
        ),
        (
            "submit_object_erase",
            submit_object_erase,
            {
                "inputVideo": str(video_path),
                "outputVideo": str(out_dir / "object_erase.mp4"),
                "objectPrompt": "logo in corner",
                "boxThreshold": 0.35,
                "textThreshold": 0.25,
                "seed": 7,
            },
        ),
        (
            "submit_text_replace",
            submit_text_replace,
            {
                "inputVideo": str(video_path),
                "outputVideo": str(out_dir / "text_replace.mp4"),
                "targetText": "SALE",
                "newText": "DROP",
                "fontSize": 48,
                "seed": 3,
            },
        ),
    ]

    covered = {name for name, _, _ in tasks}
    missing = sorted(available - covered)

    for name, fn, payload in tasks:
        try:
            result = fn(payload)
            detail = result.get("job_path") or result.get("job_id") or "job created"
            results.append({"name": name, "status": "ok", "detail": detail})
        except Exception as exc:
            results.append({"name": name, "status": "error", "detail": str(exc)})

    return results, missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a smoke test for each available tool.")
    parser.add_argument(
        "--video",
        default=str(Path(__file__).resolve().parent / "video.mp4"),
        help="Path to the video file (default: tests/video.mp4).",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "tool_smoke"),
        help="Output directory (default: tests/tool_smoke).",
    )
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    out_dir = Path(args.out).resolve()

    if not video_path.exists():
        print(f"Video not found: {video_path}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== Edit Tools ===")
    edit_results, edit_missing = _run_edit_tools(video_path, out_dir)
    for item in edit_results:
        _print_result(item)
    if edit_missing:
        print(f"Missing edit tool coverage: {', '.join(edit_missing)}")

    print("")
    print("=== Generative Tools (job specs only) ===")
    gen_results, gen_missing = _run_generative_tools(video_path, out_dir)
    for item in gen_results:
        _print_result(item)
    if gen_missing:
        print(f"Missing generative tool coverage: {', '.join(gen_missing)}")

    failures = [r for r in edit_results + gen_results if r.get("status") == "error"]
    if failures:
        print("")
        print("Some tools failed. See errors above.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
