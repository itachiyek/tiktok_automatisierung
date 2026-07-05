"""YouTube-Ingest über yt-dlp – neue Uploads eines Kanals erkennen (KEIN API-Key nötig).

Früher lief das über die YouTube Data API v3 (brauchte YOUTUBE_API_KEY + Quota).
Jetzt per yt-dlp (dasselbe Tool wie beim Download): liest den /videos-Tab eines
Kanals flat aus. yt-dlp liefert dabei Video-ID, Titel und Dauer, aber KEINE
View-Counts – deshalb Ranking nach Aktualität (neueste zuerst) statt nach Views.
Der Dauer-Filter wirft Shorts/zu kurze Videos raus (ergeben keine >=60s-Clips).
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Optional

from ..models import SourceItem, YOUTUBE


class YouTubeClient:
    def __init__(self, api_key: str = ""):
        # api_key wird nicht mehr benötigt (yt-dlp), Parameter bleibt für Kompatibilität.
        self.api_key = api_key

    def get_recent_uploads(
        self,
        channel_id: str,
        limit: int = 5,
        published_after: Optional[str] = None,  # (ungenutzt; Signatur beibehalten)
        rank_by_views: bool = True,             # (ohne API keine Views -> Aktualitäts-Ranking)
        min_duration_sec: float = 90.0,
    ) -> list[SourceItem]:
        """Neueste Quell-Videos eines Kanals (Shorts gefiltert), neueste zuerst."""
        if not channel_id or channel_id.startswith("UC_X"):
            return []  # Platzhalter-ID in der Beispiel-Config
        pool = min(50, max(limit * 4, 20))
        url = f"https://www.youtube.com/channel/{channel_id}/videos"
        # Auflisten läuft cookie-frei (robust); nur der Download (downloader.py)
        # braucht Cookies.
        cmd = [
            sys.executable, "-m", "yt_dlp", "-J", "--flat-playlist", "--no-warnings",
            "--playlist-end", str(pool), url,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
        except FileNotFoundError:
            raise RuntimeError("yt-dlp nicht gefunden (PATH).")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"yt-dlp Timeout beim Kanal-Abruf ({channel_id}).")
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            raise RuntimeError(f"yt-dlp Fehler ({channel_id}): {(proc.stderr or '')[:300]}")

        data = json.loads(proc.stdout)
        entries = data.get("entries") or []
        items: list[SourceItem] = []
        for e in entries:
            vid = e.get("id")
            if not vid:
                continue
            dur = float(e.get("duration") or 0.0)
            if dur and dur < min_duration_sec:  # Shorts/zu kurz überspringen
                continue
            views = e.get("view_count")
            items.append(
                SourceItem(
                    creator_id=channel_id,
                    platform=YOUTUBE,
                    source_id=vid,  # -> key "youtube:<id>" (Dedup-kompatibel)
                    title=e.get("title") or "",
                    url=e.get("url") or f"https://www.youtube.com/watch?v={vid}",
                    duration_sec=dur,
                    created_at="",
                    extra={"view_count": int(views) if views else 0},
                )
            )
        # Falls yt-dlp doch View-Counts liefert, danach ranken; sonst bleibt
        # die yt-dlp-Reihenfolge (= neueste zuerst) stabil erhalten.
        if rank_by_views and any(s.extra.get("view_count") for s in items):
            items.sort(key=lambda s: s.extra.get("view_count", 0), reverse=True)
        return items[:limit]
