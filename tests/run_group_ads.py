import argparse
import json
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("VIDEO_HWACCEL", "none")
os.environ.setdefault("VIDEO_ENCODER", "libx264")

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ai_agents.group_ads import generate_group_variants  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run group ad generation with OpenAI planning.")
    parser.add_argument(
        "--video",
        default=str(Path(__file__).resolve().parent / "video.mp4"),
        help="Path to the video file (default: tests/video.mp4).",
    )
    parser.add_argument(
        "--analysis",
        default=str(Path(__file__).resolve().parent / "analysis.json"),
        help="Path to the analysis json (default: tests/analysis.json).",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "group_ads"),
        help="Output directory (default: tests/group_ads).",
    )
    parser.add_argument(
        "--groups",
        type=int,
        default=3,
        help="Number of audience groups to generate (default: 3).",
    )
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH; cannot run group ads test.")
        return 1
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set; OpenAI-only planning is required.")
        return 1

    video_path = Path(args.video).resolve()
    analysis_path = Path(args.analysis).resolve()
    out_dir = Path(args.out).resolve()

    if not video_path.exists():
        print(f"Video not found: {video_path}")
        return 1

    if not analysis_path.exists():
        print(f"Analysis json not found: {analysis_path}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    with analysis_path.open("r", encoding="utf-8") as f:
        analysis = json.load(f)

    variants, metadata = generate_group_variants(
        video_id="test",
        original_path=video_path,
        analysis=analysis,
        processed_dir=out_dir,
        csv_path=str(BACKEND_DIR / "mock_profiles.csv"),
        group_count=args.groups,
        max_edits=1,
    )

    if not variants:
        print("No variants generated.")
        return 1

    missing = []
    for variant in variants:
        path = out_dir / Path(variant["url"]).name
        if not path.exists():
            missing.append(str(path))

    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Generated {len(variants)} variants.")
    for item in metadata:
        summary = item.get("summary") or "(no summary)"
        print(f"- group {item.get('groupId')}: {summary}")
    print(f"Metadata saved to: {metadata_path}")

    if missing:
        print("Missing output files:")
        for path in missing:
            print(f"- {path}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
