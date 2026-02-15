"""
MCP Server for Video Editor — exposes tools that route all requests through
the orchestrator agent (ai_agents/orchestrator.py).

Poke user -> Poke AI -> MCP edit_video -> run_orchestrator_agent -> OpenAI -> tools -> FFmpeg

Local dev:
    python mcp_server.py

Cloud (Render):
    Deployed via Dockerfile — Render sets PORT automatically.
    Users add https://<your-service>.onrender.com/mcp in Poke settings.
"""

import json
import os
import shutil
import traceback
import urllib.request
import uuid
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse

from ai_agents.orchestrator import run_orchestrator_agent

load_dotenv()

# ---------------------------------------------------------------------------
# Storage paths  (use /tmp on cloud where filesystem is ephemeral)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
_cloud = os.getenv("RENDER", "")  # Render sets this automatically
STORAGE_DIR = Path("/tmp/adapt-storage") if _cloud else BASE_DIR / "storage"
ORIGINAL_DIR = STORAGE_DIR / "original"
PROCESSED_DIR = STORAGE_DIR / "processed"
ANALYSIS_DIR = STORAGE_DIR / "analysis"

for _dir in (ORIGINAL_DIR, PROCESSED_DIR, ANALYSIS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Base URL for download links
# ---------------------------------------------------------------------------

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
if _cloud and not RENDER_URL:
    RENDER_URL = "https://adapt-q15d.onrender.com"

LOCAL_BASE = "http://localhost:{port}"

# ---------------------------------------------------------------------------
# Port config
# ---------------------------------------------------------------------------

if _cloud:
    MCP_PORT = int(os.getenv("PORT", "10000"))
else:
    MCP_PORT = int(os.getenv("MCP_PORT", "8765"))


def _base_url() -> str:
    if _cloud and RENDER_URL:
        return RENDER_URL
    return LOCAL_BASE.format(port=MCP_PORT)


# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "ADAPT Video Editor",
    instructions=(
        "You are ADAPT, an AI video editing assistant. You edit videos using "
        "natural language instructions.\n\n"
        "WORKFLOW:\n"
        "1. If the user has already provided a video URL, skip to step 2.\n"
        "   Otherwise call list_videos to see what's available.\n"
        "2. Call edit_video with the video source (URL or filename) and a "
        "   natural language description of the edits.\n\n"
        "The AI orchestrator will figure out which tools to use (speed change, "
        "color grade, trim, text overlay, reframe, film grain, combos, etc.).\n\n"
        "After editing, you'll receive a download URL for the processed video."
    ),
    host="0.0.0.0",
    port=MCP_PORT,
)

# ---------------------------------------------------------------------------
# Extra HTTP routes (custom_route — served alongside MCP by FastMCP)
# ---------------------------------------------------------------------------


@mcp.custom_route("/files/{filename}", methods=["GET", "HEAD"])
async def download_file(request: Request) -> FileResponse | JSONResponse:
    """Serve a processed video file for download."""
    filename = request.path_params["filename"]
    safe_name = Path(filename).name

    # Search in multiple directories for the file
    for search_dir in (PROCESSED_DIR, ORIGINAL_DIR, STORAGE_DIR):
        file_path = search_dir / safe_name
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path), media_type="video/mp4", filename=safe_name)

    return JSONResponse({"error": f"File not found: {safe_name}"}, status_code=404)


@mcp.custom_route("/", methods=["GET", "HEAD"])
async def health_check(request: Request) -> PlainTextResponse:
    """Health check — Render pings HEAD / to confirm the service is alive."""
    return PlainTextResponse("ok")


@mcp.custom_route("/debug/ffmpeg", methods=["GET"])
async def debug_ffmpeg(request: Request) -> JSONResponse:
    """Diagnostic endpoint — show FFmpeg version, encoders, and storage info."""
    import subprocess as _sp

    info = {}
    try:
        r = _sp.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        info["version"] = (r.stdout or "").split("\n")[0]
    except Exception as e:
        info["version_error"] = str(e)

    try:
        r = _sp.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10)
        lines = [l for l in (r.stdout or "").split("\n") if "264" in l or "aac" in l.lower()]
        info["relevant_encoders"] = lines
    except Exception as e:
        info["encoders_error"] = str(e)

    try:
        from ai_agents.video import ENCODER, HWACCEL
        info["selected_encoder"] = ENCODER
        info["hwaccel"] = HWACCEL
    except Exception as e:
        info["encoder_import_error"] = str(e)

    info["storage_dir"] = str(STORAGE_DIR)
    info["processed_dir_exists"] = PROCESSED_DIR.exists()
    info["original_files"] = [f.name for f in ORIGINAL_DIR.iterdir()] if ORIGINAL_DIR.exists() else []
    info["processed_files"] = [f.name for f in PROCESSED_DIR.iterdir()] if PROCESSED_DIR.exists() else []

    return JSONResponse(info)


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
        print(f"[download] Fetching {video_source} -> {local_path}")
        urllib.request.urlretrieve(video_source, str(local_path))
        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"[download] Saved {size_mb:.1f} MB")
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


def _download_url(file_path: str) -> str:
    """Build a public download URL for a processed file."""
    name = Path(file_path).name
    return f"{_base_url()}/files/{name}"


def _ensure_in_processed_dir(file_path: str) -> str:
    """If the file is outside PROCESSED_DIR, move it there and return the new path."""
    p = Path(file_path).resolve()
    processed = PROCESSED_DIR.resolve()
    if p.parent == processed:
        return str(p)
    if p.exists() and p.is_file():
        dest = processed / p.name
        shutil.move(str(p), str(dest))
        print(f"[fix] Moved {p} -> {dest}")
        return str(dest)
    return file_path


def _verify_output(file_path: str) -> dict:
    """Check that the output file exists and has content."""
    p = Path(file_path)
    if not p.exists():
        return {"verified": False, "error": "Output file was not created"}
    size = p.stat().st_size
    if size < 1000:
        return {"verified": False, "error": f"Output file is suspiciously small ({size} bytes)"}
    return {"verified": True, "size_mb": round(size / (1024 * 1024), 2)}


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_videos() -> str:
    """List all available videos (originals and processed results).
    Call this FIRST to see what videos are available before editing.
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
        lines.append("No original videos found. Provide a video URL to edit_video.")

    processed = sorted(
        f for f in PROCESSED_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS
    )
    if processed:
        lines.append("\nProcessed videos:")
        for f in processed:
            size_mb = f.stat().st_size / (1024 * 1024)
            dl = _download_url(str(f))
            lines.append(f"  - {f.name}  ({size_mb:.1f} MB)  Download: {dl}")

    return "\n".join(lines)


@mcp.tool()
def edit_video(video_source: str, instructions: str) -> str:
    """Edit a video using natural language instructions. The AI orchestrator
    interprets the request and calls the right tool (speed change, color grade,
    trim, reverse, reframe, film grain, text overlay, presets, generative edits,
    or market research).

    video_source can be:
      - A public URL (https://...) — the video will be downloaded automatically
      - A filename from list_videos

    Examples:
      - "Speed this up slightly"
      - "Make it look cinematic with film grain"
      - "Trim to the first 5 seconds and add a caption saying WAIT FOR IT"
      - "Reframe for TikTok vertical format"
      - "Color grade with warm tones"
      - "Reverse the video"

    Args:
        video_source: Public video URL (https://...) or filename from list_videos.
        instructions: Natural language description of what you want done.
    """
    # --- Step 1: Resolve input ---
    try:
        inp = _resolve_input(video_source)
    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error downloading/finding video: {e}"

    inp_size = Path(inp).stat().st_size / (1024 * 1024)
    print(f"[edit] Input: {inp} ({inp_size:.1f} MB)")
    print(f"[edit] Instructions: {instructions}")

    out = _output_path("edited")

    # --- Step 2: Run orchestrator ---
    try:
        result = run_orchestrator_agent(
            request=instructions,
            input_path=inp,
            output_path=out,
        )
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[edit] Orchestrator error: {tb}")
        # Include FFmpeg stderr if available (CalledProcessError)
        stderr_info = ""
        if hasattr(e, "stderr") and e.stderr:
            stderr_info = f"\nFFmpeg output: {str(e.stderr)[-500:]}"
        elif hasattr(e, "__cause__") and hasattr(e.__cause__, "stderr") and e.__cause__.stderr:
            stderr_info = f"\nFFmpeg output: {str(e.__cause__.stderr)[-500:]}"
        return f"Error during processing: {e}{stderr_info}"

    # --- Step 3: Parse orchestrator result ---
    parsed = {}
    output_file = out

    if isinstance(result, dict) and result.get("role") == "tool":
        content = result.get("content", "{}")
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            parsed = {"raw": content}
        output_file = parsed.get("outputPath", out)
    elif isinstance(result, dict) and result.get("error"):
        return f"Error: {result['error']}"
    else:
        return f"Unexpected orchestrator result: {json.dumps(result)}"

    # --- Step 4: Ensure file is in PROCESSED_DIR (safety net) ---
    output_file = _ensure_in_processed_dir(output_file)

    # Also check the expected default path in case LLM wrote there
    if not Path(output_file).exists() and Path(out).exists():
        output_file = out
        print(f"[edit] Fell back to expected output path: {out}")

    # --- Step 5: Verify the output file actually exists ---
    check = _verify_output(output_file)
    if not check["verified"]:
        print(f"[edit] VERIFICATION FAILED: {check['error']}")
        # Last resort: scan PROCESSED_DIR for the most recently created file
        candidates = sorted(
            PROCESSED_DIR.glob("*.mp4"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            output_file = str(candidates[0])
            check = _verify_output(output_file)
            print(f"[edit] Found latest processed file: {output_file}")

    if not check.get("verified"):
        return (
            f"Processing reported success but verification failed: {check.get('error', 'unknown')}. "
            f"The edit may not have been applied correctly."
        )

    # --- Step 6: Build response with download URL ---
    dl_url = _download_url(output_file)
    size_mb = check["size_mb"]

    lines = [
        "Edit complete!",
        f"Output file: {Path(output_file).name}",
        f"Output size: {size_mb} MB",
        f"Download URL: {dl_url}",
    ]

    if parsed.get("error"):
        lines.append(f"Warning: {parsed['error']}")
    if parsed.get("jobId"):
        lines.append(f"Generative job submitted: {parsed['jobId']}")

    print(f"[edit] Success: {dl_url} ({size_mb} MB)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Starting ADAPT Video Editor MCP server on port {MCP_PORT}...")
    print(f"Storage: {STORAGE_DIR}")
    print(f"Base URL: {_base_url()}")
    print(f"\nTools available:")
    print(f"  - list_videos   -- See available videos")
    print(f"  - edit_video    -- Edit video via AI orchestrator (natural language)")
    print(f"\nEndpoints:")
    print(f"  - /mcp           -- MCP protocol (for Poke)")
    print(f"  - /files/{{name}} -- Download processed videos")
    print(f"  - /              -- Health check")
    if _cloud:
        print(f"\nRunning in cloud mode (Render).")
        print(f"Add in Poke settings → Connections → Create Integration:")
        print(f"  Server URL: {_base_url()}/mcp")
    else:
        print(f"\nLocal dev — in another terminal, run:")
        print(f'  npx poke tunnel http://localhost:{MCP_PORT}/mcp -n "Video Editor"')
    print()
    mcp.run(transport="streamable-http")
