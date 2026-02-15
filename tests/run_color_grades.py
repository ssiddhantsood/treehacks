from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.ai_agents.video import color_grade_video

PRESETS = {
    "neutral_clean": {"contrast": 1.05, "brightness": 0.02, "saturation": 1.0},
    "bright_airy": {"contrast": 1.02, "brightness": 0.06, "saturation": 1.05},
    "moody_dark": {"contrast": 1.12, "brightness": -0.03, "saturation": 0.92},
    "warm_glow": {"contrast": 1.06, "brightness": 0.03, "saturation": 1.08},
    "cool_urban": {"contrast": 1.08, "brightness": 0.0, "saturation": 0.98},
    "vibrant_pop": {"contrast": 1.1, "brightness": 0.02, "saturation": 1.18},
    "soft_pastel": {"contrast": 0.98, "brightness": 0.04, "saturation": 0.9},
}


def _write_gallery(out_dir: Path, items: list[tuple[str, Path]]) -> None:
    cards = "\n".join(
        [
            f"""
      <div class="card">
        <h3>{name}</h3>
        <video src="{path.name}" controls preload="metadata"></video>
      </div>
            """.strip()
            for name, path in items
        ]
    )
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Color Grade Variants</title>
    <style>
      body {{
        font-family: "Georgia", serif;
        margin: 32px;
        background: #111;
        color: #f2f2f2;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 20px;
      }}
      .card {{
        background: #1c1c1c;
        border-radius: 14px;
        padding: 16px;
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.35);
      }}
      video {{
        width: 100%;
        border-radius: 10px;
        background: #000;
      }}
    </style>
  </head>
  <body>
    <h1>Color Grade Variants</h1>
    <p>Source: video.mp4</p>
    <div class="grid">
      {cards}
    </div>
  </body>
</html>
"""
    (out_dir / "index.html").write_text(html)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate color grading variants.")
    parser.add_argument(
        "--video",
        type=Path,
        default=Path(__file__).with_name("video.mp4"),
        help="Path to input video.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).with_name("graded"),
        help="Output folder for graded videos.",
    )
    parser.add_argument("--html", dest="html", action="store_true", help="Write an HTML gallery.")
    parser.add_argument("--no-html", dest="html", action="store_false")
    parser.set_defaults(html=True)

    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"Input video not found: {args.video}")

    args.out.mkdir(parents=True, exist_ok=True)

    outputs: list[tuple[str, Path]] = []
    for name, grade in PRESETS.items():
        output_path = args.out / f"video-{name}.mp4"
        color_grade_video(
            str(args.video),
            str(output_path),
            contrast=float(grade["contrast"]),
            brightness=float(grade["brightness"]),
            saturation=float(grade["saturation"]),
        )
        outputs.append((name, output_path))

    if args.html:
        _write_gallery(args.out, outputs)

    print(f"Wrote {len(outputs)} variants to {args.out}")
    if args.html:
        print(f"Gallery: {args.out / 'index.html'}")


if __name__ == "__main__":
    main()
