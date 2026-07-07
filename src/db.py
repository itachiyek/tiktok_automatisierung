"""SQLite-Zustandsspeicher (Dedup + Clip-Status). Migration zu Supabase später möglich."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

from .config import DATA_DIR, DB_PATH
from .models import Clip, ClipMeta, Segment

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_sources (
  source_key   TEXT PRIMARY KEY,
  creator_id   TEXT,
  processed_at REAL
);
CREATE TABLE IF NOT EXISTS clips (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id  TEXT NOT NULL,
  source_key  TEXT NOT NULL,
  start       REAL NOT NULL,
  end         REAL NOT NULL,
  score       REAL DEFAULT 0,
  path        TEXT DEFAULT '',
  title       TEXT DEFAULT '',
  caption     TEXT DEFAULT '',
  hashtags    TEXT DEFAULT '[]',
  status      TEXT DEFAULT 'new',
  tiktok_id   TEXT DEFAULT '',
  created_at  REAL,
  UNIQUE(creator_id, source_key, start, end)
);
"""


def connect(path=None) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path or DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None) -> sqlite3.Connection:
    c = conn or connect()
    c.executescript(SCHEMA)
    c.commit()
    return c


# --- processed_sources ---------------------------------------------------
def is_processed(conn, source_key: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM processed_sources WHERE source_key=?", (source_key,)
    ).fetchone()
    return row is not None


def mark_processed(conn, source_key: str, creator_id: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO processed_sources(source_key, creator_id, processed_at) "
        "VALUES (?,?,?)",
        (source_key, creator_id, time.time()),
    )
    conn.commit()


# --- clips ---------------------------------------------------------------
def used_ranges(conn, creator_id: str, source_key: str) -> list[tuple[float, float]]:
    """Bereits verwendete Zeitbereiche einer Quelle (für die VOD-Wiederverwendung)."""
    rows = conn.execute(
        "SELECT start, end FROM clips WHERE creator_id=? AND source_key=?",
        (creator_id, source_key),
    ).fetchall()
    return [(float(r["start"]), float(r["end"])) for r in rows]


def clip_exists(conn, creator_id: str, source_key: str, start: float, end: float) -> bool:
    row = conn.execute(
        "SELECT 1 FROM clips WHERE creator_id=? AND source_key=? "
        "AND ABS(start-?)<0.5 AND ABS(end-?)<0.5",
        (creator_id, source_key, start, end),
    ).fetchone()
    return row is not None


def save_clip(conn, clip: Clip) -> int:
    meta = clip.meta or ClipMeta("", "", [])
    cur = conn.execute(
        "INSERT OR IGNORE INTO clips"
        "(creator_id, source_key, start, end, score, path, title, caption, hashtags,"
        " status, tiktok_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            clip.creator_id,
            clip.source_key,
            clip.segment.start,
            clip.segment.end,
            clip.segment.score,
            clip.path,
            meta.title,
            meta.caption,
            json.dumps(meta.hashtags, ensure_ascii=False),
            clip.status,
            clip.tiktok_id,
            time.time(),
        ),
    )
    conn.commit()
    if cur.lastrowid:
        clip.id = cur.lastrowid
    return clip.id or 0


def update_status(conn, clip_id: int, status: str, tiktok_id: str = "") -> None:
    if tiktok_id:
        conn.execute(
            "UPDATE clips SET status=?, tiktok_id=? WHERE id=?",
            (status, tiktok_id, clip_id),
        )
    else:
        conn.execute("UPDATE clips SET status=? WHERE id=?", (status, clip_id))
    conn.commit()


def _row_to_clip(row: sqlite3.Row) -> Clip:
    return Clip(
        id=row["id"],
        creator_id=row["creator_id"],
        source_key=row["source_key"],
        segment=Segment(row["start"], row["end"], row["score"]),
        path=row["path"],
        meta=ClipMeta(row["title"], row["caption"], json.loads(row["hashtags"] or "[]")),
        status=row["status"],
        tiktok_id=row["tiktok_id"],
    )


def list_clips(conn, status: Optional[str] = None, creator_id: Optional[str] = None) -> list[Clip]:
    q = "SELECT * FROM clips WHERE 1=1"
    args: list = []
    if status:
        q += " AND status=?"
        args.append(status)
    if creator_id:
        q += " AND creator_id=?"
        args.append(creator_id)
    q += " ORDER BY id DESC"
    return [_row_to_clip(r) for r in conn.execute(q, args).fetchall()]


def get_clip(conn, clip_id: int) -> Optional[Clip]:
    row = conn.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
    return _row_to_clip(row) if row else None
