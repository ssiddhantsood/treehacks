import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ai_agents.action_timeline import analyze_video  # noqa: E402


def _print_section(title: str, items: list[dict], formatter) -> None:
    print("")
    print(f"=== {title} ===")
    if not items:
        print("(none)")
        return
    for item in items:
        print(formatter(item))


def _fmt_per_second(item: dict) -> str:
    t = f"{item.get('t', 0.0):>7.3f}s"
    desc = item.get("description", "") or ""
    people = ", ".join(item.get("people") or [])
    objects = ", ".join(item.get("objects") or [])
    actions = ", ".join(item.get("actions") or [])
    setting = item.get("setting", "") or ""
    confidence = item.get("confidence", 0.0)
    parts = [desc]
    if people:
        parts.append(f"people=[{people}]")
    if objects:
        parts.append(f"objects=[{objects}]")
    if actions:
        parts.append(f"actions=[{actions}]")
    if setting:
        parts.append(f"setting={setting}")
    if confidence:
        parts.append(f"conf={confidence:.2f}")
    return f"{t} | " + " | ".join([p for p in parts if p])


def _fmt_scene_segment(item: dict) -> str:
    t_start = f"{item.get('t_start', 0.0):>7.3f}s"
    t_end = f"{item.get('t_end', 0.0):>7.3f}s"
    desc = item.get("description", "") or ""
    elements = ", ".join(item.get("key_elements") or [])
    confidence = item.get("confidence", 0.0)
    parts = [desc]
    if elements:
        parts.append(f"elements=[{elements}]")
    if confidence:
        parts.append(f"conf={confidence:.2f}")
    return f"{t_start} -> {t_end} | " + " | ".join([p for p in parts if p])


def _fmt_justification(item: dict) -> str:
    t = f"{item.get('t', 0.0):>7.3f}s"
    text = item.get("justification", "") or ""
    return f"{t} | {text}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run action timeline analysis and print readable output.")
    parser.add_argument(
        "--video",
        default=str(Path(__file__).resolve().parent / "video.mp4"),
        help="Path to the video file (default: tests/video.mp4).",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "analysis.json"),
        help="Path for the output JSON (default: tests/analysis.json).",
    )
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    output_path = Path(args.out).resolve()

    if not video_path.exists():
        print(f"Video not found: {video_path}")
        return 1

    result = analyze_video(str(video_path), str(output_path))

    print("=== Summary ===")
    print(f"Video: {video_path}")
    print(f"Output JSON: {output_path}")
    print(f"Duration: {result.get('duration', 0.0)}s")
    print(f"Scene cuts: {len(result.get('scene_cuts', []))}")
    print(f"Per-second descriptions: {len(result.get('per_second_descriptions', []))}")
    print(f"Scene segments: {len(result.get('scene_segments', []))}")
    print(f"Justification timeline: {len(result.get('justification_timeline', []))}")

    _print_section("Per-Second Descriptions", result.get("per_second_descriptions", []), _fmt_per_second)
    _print_section("Scene Segments", result.get("scene_segments", []), _fmt_scene_segment)
    _print_section("Justification Timeline", result.get("justification_timeline", []), _fmt_justification)

    print("")
    print("=== Raw Result (truncated) ===")
    print(json.dumps({k: v for k, v in result.items() if k not in {"per_second_descriptions", "scene_segments", "justification_timeline"}}, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
