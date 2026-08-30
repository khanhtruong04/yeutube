"""
SQLite store cho job web (Phase 0-2) — tách biệt hoàn toàn với index.csv của
crawler/CLI hiện có, không đụng vào store.py.
"""
import asyncio
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "jobs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    video_url TEXT NOT NULL,
    title TEXT,
    platform TEXT,
    provider TEXT,
    voice_code TEXT,
    voice_gender TEXT DEFAULT 'female',
    whisper_model TEXT DEFAULT 'base',
    stt_language TEXT,
    target_language TEXT DEFAULT 'vi',
    volume_goc REAL DEFAULT 0.10,
    volume_dub REAL DEFAULT 1.0,
    speed REAL,
    status TEXT DEFAULT 'queued',
    error TEXT,
    folder TEXT,
    video_width INTEGER,
    video_height INTEGER,
    video_duration REAL,
    masks_json TEXT,
    text_layout_json TEXT,
    target_resolution INTEGER DEFAULT 1080,
    upscale INTEGER DEFAULT 0,
    subtitles_enabled INTEGER DEFAULT 1,
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db_sync() -> None:
    with _conn() as conn:
        conn.execute(_SCHEMA)


async def init_db() -> None:
    await asyncio.to_thread(_init_db_sync)


def _create_job_sync(fields: dict) -> dict:
    job_id = uuid.uuid4().hex
    now = datetime.now().isoformat(timespec="seconds")
    row = {
        "id": job_id,
        "video_url": fields["video_url"],
        "title": fields.get("title"),
        "platform": fields.get("platform"),
        "provider": fields.get("provider"),
        "voice_code": fields.get("voice_code"),
        "voice_gender": fields.get("voice_gender") or "female",
        "whisper_model": fields.get("whisper_model") or "base",
        "stt_language": fields.get("stt_language"),
        "target_language": fields.get("target_language") or "vi",
        "volume_goc": fields.get("volume_goc") if fields.get("volume_goc") is not None else 0.10,
        "volume_dub": fields.get("volume_dub") if fields.get("volume_dub") is not None else 1.0,
        "speed": fields.get("speed"),
        "target_resolution": fields.get("target_resolution") or 1080,
        "upscale": int(bool(fields.get("upscale"))),
        "status": "queued",
        "error": None,
        "folder": None,
        "subtitles_enabled": 1,
        "progress_current": 0,
        "progress_total": 0,
        "created_at": now,
        "updated_at": now,
    }
    cols = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    with _conn() as conn:
        conn.execute(f"INSERT INTO jobs ({cols}) VALUES ({placeholders})", row)
    return row


async def create_job(**fields) -> dict:
    return await asyncio.to_thread(_create_job_sync, fields)


def _update_job_sync(job_id: str, fields: dict) -> None:
    if not fields:
        return
    fields = {**fields, "updated_at": datetime.now().isoformat(timespec="seconds")}
    set_clause = ", ".join(f"{k} = :{k}" for k in fields.keys())
    with _conn() as conn:
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = :id", {**fields, "id": job_id})


async def update_job(job_id: str, **fields) -> None:
    await asyncio.to_thread(_update_job_sync, job_id, fields)


def _get_job_sync(job_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


async def get_job(job_id: str) -> dict | None:
    return await asyncio.to_thread(_get_job_sync, job_id)


def _list_jobs_sync(limit: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


async def list_jobs(limit: int = 50) -> list[dict]:
    return await asyncio.to_thread(_list_jobs_sync, limit)
