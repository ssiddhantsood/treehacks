"""
MCP Server for Video Editor — exposes tools that route all requests through
the orchestrator agent (ai_agents/orchestrator.py).

Poke user → Poke AI → MCP edit_video → run_orchestrator_agent → OpenAI → tools → FFmpeg

Run:
    python mcp_server.py

Then in another terminal:
    npx poke tunnel http://localhost:8765/mcp -n "Video Editor"
"""

import json
import os
import urllib.request
import uuid
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from ai_agents.orchestrator import run_orchestrator_agent

load_dotenv()

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
ORIGINAL_DIR = STORAGE_DIR / "original"
PROCESSED_DIR = STORAGE_DIR / "processed"
ANALYSIS_DIR = STORAGE_DIR / "analysis"

for _dir in (ORIGINAL_DIR, PROCESSED_DIR, ANALYSIS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------

MCP_PORT = int(os.getenv("MCP_PORT", "8765"))

mcp = FastMCP(
    "Video Editor",
    instructions=(
        "You are a video editing assistant that processes videos on the user's "
        "local machine. IMPORTANT: Always call list_videos first to see what "
        "videos are available. Then call edit_video with the filename and a "
        "natural language description of the edits you want. The AI orchestrator "
        "will figure out which video tools to use."
    ),
    host="0.0.0.0",
    port=MCP_PORT,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_input(video_source: str) -> str:
    """Download a video from a URL, or find it locally."""
    if video_source.startswith(("http://", "https://")):
        ext = Path(video_source).suffix or ".mp4"
        if len(ext) > 5 or "?" in ext:
            ext = ".mp4"
        filename = f"{uuid.uuid4().hex}{ext}"
        local_path = ORIGINAL_DIR / filename
        urllib.request.urlretrieve(video_source, str(local_path))
        return str(local_path)

    p = Path(video_source)
    if p.exists():
        return str(p)

    name = Path(video_source).name
    for search_dir in (ORIGINAL_DIR, PROCESSED_DIR):
        candidate = search_dir / name
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(
        f"Video not found: {video_source}. Use list_videos to see available files."
    )


def _output_path(label: str) -> str:
    filename = f"{uuid.uuid4().hex}-{label}.mp4"
    return str(PROCESSED_DIR / filename)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_videos() -> str:
    """List all available videos (originals and processed results).
    Call this FIRST to see what videos are on the user's machine before editing.
    Use the filename from the output as video_source in other tools.
    """
    VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    lines = []

    originals = sorted(
        f for f in ORIGINAL_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS
    )
    if originals:
        lines.append("Original videos:")
        for f in originals:
            size_mb = f.stat().st_size / (1024 * 1024)
            lines.append(f"  - {f.name}  ({size_mb:.1f} MB)")
    else:
        lines.append("No original videos found.")

    processed = sorted(
        f for f in PROCESSED_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS
    )
    if processed:
        lines.append("\nProcessed videos:")
        for f in processed:
            size_mb = f.stat().st_size / (1024 * 1024)
            lines.append(f"  - {f.name}  ({size_mb:.1f} MB)")

    return "\n".join(lines)


@mcp.tool()
def edit_video(video_source: str, instructions: str) -> str:
    """Edit a video using natural language instructions. The AI orchestrator
    interprets the request and calls the right tool (speed change, color grade,
    trim, reverse, reframe, film grain, text overlay, presets, generative edits,
    or market research).

    Examples:
      - "Speed this up 2x"
      - "Make it look cinematic with film grain"
      - "Trim to the first 5 seconds and add a caption"
      - "Reframe for TikTok vertical format"
      - "Color grade with high contrast and warm tones"
      - "Reverse the video"
      - "Replace the background with a beach scene"
      - "Who is the target audience for this ad?"

    Args:
        video_source: Filename from list_videos, URL, or local path.
        instructions: Natural language description of what you want done.
    """
    inp = _resolve_input(video_source)
    out = _output_path("edited")

    result = run_orchestrator_agent(
        request=instructions,
        input_path=inp,
        output_path=out,
    )

    # result is the last tool output dict from the orchestrator
    if isinstance(result, dict) and result.get("role") == "tool":
        content = result.get("content", "{}")
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": content}

        output_path = parsed.get("outputPath", out)
        lines = ["Edit complete."]
        if parsed.get("ok"):
            lines.append(f"Output: {output_path}")
        if parsed.get("error"):
            lines.append(f"Error: {parsed['error']}")
        if parsed.get("jobId"):
            lines.append(f"Generative job submitted: {parsed['jobId']}")
        return "\n".join(lines)

    return f"Orchestrator result: {json.dumps(result)}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Starting Video Editor MCP server on port {MCP_PORT}...")
    print(f"\nTools available:")
    print(f"  - list_videos   -- See available videos")
    print(f"  - edit_video    -- Edit video via AI orchestrator (natural language)")
    print(f"\nNext step -- in another terminal, run:")
    print(f'  npx poke tunnel http://localhost:{MCP_PORT}/mcp -n "Video Editor"\n')
    mcp.run(transport="streamable-http")
