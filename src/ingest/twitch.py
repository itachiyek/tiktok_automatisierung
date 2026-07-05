"""Twitch-Ingest über yt-dlp (KEIN API-Key nötig) – Community-Clips + VODs.

Früher lief das über die Twitch-Helix-API (TWITCH_CLIENT_ID/SECRET). Jetzt per
yt-dlp: liest die /clips- und /videos-Seiten eines Kanals flat aus. yt-dlp liefert
für VODs echte Dauer + View-Count → Ranking nach Views und korrektes Fenstern
langer Streams (statt mehrere GB komplett zu laden).

Twitch ist – anders als YouTube – ohne Cookies/PO-Token zuverlässig ladbar.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Optional

from ..models import SourceItem, TWITCH_CLIP, TWITCH_VOD


def _entries(url: str, limit: int) -> list[dict]:
    cmd = [
        sys.executable, "-m", "yt_dlp", "-J", "--flat-playlist", "--no-warnings",
        "--playlist-end", str(max(1, limit)), url,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90
        )
    except Exception:
        return []
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return []
    try:
        return json.loads(proc.stdout).get("entries") or []
    except Exception:
        return []


class TwitchClient:
    def __init__(self, client_id: str = "", client_secret: str = ""):
        # API-Keys werden nicht mehr benötigt (yt-dlp); Parameter bleiben für Kompatibilität.
        self.client_id = client_id
        self.client_secret = client_secret

    def get_clips(self, login: str, started_at: Optional[str] = None, limit: int = 20) -> list[SourceItem]:
        """Community-Clips (kuratierte Highlights). Hinweis: meist <=60s → für die
        61s-Mindestregel oft zu kurz; VODs sind die Hauptquelle."""
        items = []
        for e in _entries(f"https://www.twitch.tv/{login}/clips", limit):
            sid = e.get("id") or (e.get("url", "").rsplit("/", 1)[-1])
            if not sid:
                continue
            items.append(
                SourceItem(
                    creator_id=login, platform=TWITCH_CLIP, source_id=str(sid),
                    title=e.get("title") or "", url=e.get("url") or "",
                    duration_sec=float(e.get("duration") or 0.0), created_at="",
                    extra={"view_count": int(e.get("view_count") or 0)},
                )
            )
        return items

    def get_vods(self, login: str, limit: int = 5) -> list[SourceItem]:
        """Archivierte VODs (mehrstündige Streams) – für eigene Highlight-Erkennung."""
        items = []
        for e in _entries(f"https://www.twitch.tv/{login}/videos", limit):
            sid = e.get("id") or (e.get("url", "").rsplit("/", 1)[-1])
            if not sid:
                continue
            dur = float(e.get("duration") or 0.0)
            # Unbekannte Dauer -> als "lang" behandeln, damit gefenstert statt komplett geladen wird.
            if dur <= 0:
                dur = 99999.0
            items.append(
                SourceItem(
                    creator_id=login, platform=TWITCH_VOD, source_id=str(sid).lstrip("v"),
                    title=e.get("title") or "", url=e.get("url") or f"https://www.twitch.tv/videos/{sid}",
                    duration_sec=dur, created_at="",
                    extra={"view_count": int(e.get("view_count") or 0)},
                )
            )
        if any(s.extra.get("view_count") for s in items):
            items.sort(key=lambda s: s.extra.get("view_count", 0), reverse=True)
        return items
