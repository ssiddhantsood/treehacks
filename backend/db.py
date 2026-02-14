import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATABASE_PATH = os.getenv("DATABASE_PATH") or str(Path(__file__).resolve().parent / "storage" / "app.db")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            original_url TEXT NOT NULL,
            analysis_url TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (video_id) REFERENCES videos(id)
        )
        """
    )
    conn.commit()
    conn.close()


def create_user(email: str, password_hash: str) -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email, password_hash, _utc_now()),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return {"id": user_id, "email": email}


def get_user_by_email(email: str) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_video(
    video_id: str,
    user_id: int,
    original_url: str,
    analysis_url: str | None,
    metadata: dict | None,
) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO videos (id, user_id, original_url, analysis_url, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            video_id,
            user_id,
            original_url,
            analysis_url,
            json.dumps(metadata) if metadata else None,
            _utc_now(),
        ),
    )
    conn.commit()
    conn.close()


def add_variant(video_id: str, name: str, url: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO variants (video_id, name, url, created_at) VALUES (?, ?, ?, ?)",
        (video_id, name, url, _utc_now()),
    )
    conn.commit()
    conn.close()


def list_videos_for_user(user_id: int) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, original_url, analysis_url, metadata, created_at FROM videos WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    videos = []
    for row in rows:
        metadata = json.loads(row["metadata"]) if row["metadata"] else None
        videos.append(
            {
                "id": row["id"],
                "originalUrl": row["original_url"],
                "analysisUrl": row["analysis_url"],
                "metadata": metadata,
                "createdAt": row["created_at"],
            }
        )
    return videos


def get_video_with_variants(video_id: str, user_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, original_url, analysis_url, metadata, created_at FROM videos WHERE id = ? AND user_id = ?",
        (video_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    cur.execute(
        "SELECT name, url, created_at FROM variants WHERE video_id = ? ORDER BY created_at ASC",
        (video_id,),
    )
    variants = [dict(v) for v in cur.fetchall()]
    conn.close()

    metadata = json.loads(row["metadata"]) if row["metadata"] else None
    return {
        "id": row["id"],
        "originalUrl": row["original_url"],
        "analysisUrl": row["analysis_url"],
        "variants": variants,
        "metadata": metadata,
        "createdAt": row["created_at"],
    }
