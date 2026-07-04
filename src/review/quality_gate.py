"""Dedup + Mindestqualität; bestimmt den Status (Review nötig oder direkt freigegeben)."""
from __future__ import annotations

import os
from typing import Tuple

from .. import db
from ..models import Clip


def check(conn, clip: Clip, clip_cfg: dict) -> Tuple[bool, str]:
    """Gibt (ok, grund) zurück. ok=False -> Clip wird nicht weiterverarbeitet."""
    if not clip.path or not os.path.exists(clip.path):
        return False, "Datei fehlt"
    if os.path.getsize(clip.path) < 50_000:
        return False, "Datei zu klein / Render fehlgeschlagen"

    dur = clip.segment.duration
    min_d = float(clip_cfg.get("min_duration_sec", 60)) * 0.6
    # Harte Obergrenze bei max_duration (+3 s Encoder-Toleranz) -> bleibt im 1–2-min-Fenster.
    max_d = float(clip_cfg.get("max_duration_sec", 120)) + 3.0
    if dur < min_d:
        return False, f"zu kurz ({dur:.0f}s)"
    if dur > max_d:
        return False, f"zu lang ({dur:.0f}s)"

    if db.clip_exists(conn, clip.creator_id, clip.source_key, clip.segment.start, clip.segment.end):
        return False, "Duplikat"
    return True, "ok"


def decide_status(clip_cfg: dict, auto_approve: bool = False) -> str:
    """pending_review wenn manuelle Freigabe verlangt wird, sonst approved.

    `auto_approve=True` (z. B. im Cron-`auto`-Lauf) überschreibt die Review-Pflicht.
    """
    if auto_approve:
        return "approved"
    return "pending_review" if clip_cfg.get("require_human_review", True) else "approved"
