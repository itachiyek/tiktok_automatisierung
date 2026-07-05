"""Download von Quell-Videos via yt-dlp (Twitch-Clips/VODs, YouTube)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def download(
    url: str,
    out_dir,
    basename: str,
    start_sec: Optional[float] = None,
    dur_sec: Optional[float] = None,
) -> Optional[str]:
    """Lädt `url` nach out_dir/basename.<ext> und gibt den finalen Pfad zurück.

    Mit `start_sec`/`dur_sec` wird nur dieses Zeitfenster geladen (wichtig für
    stundenlange VODs – statt mehrerer GB nur ein paar hundert MB).
    """
    import yt_dlp  # lazy

    from ..config import ytdlp_cookie_opts  # lazy, um Import-Zyklen zu vermeiden

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "outtmpl": str(out_dir / f"{basename}.%(ext)s"),
        # 720p reicht fürs 9:16-TikTok und macht Cloud-Läufe deutlich schneller/leichter.
        "format": "bv*[height<=720]+ba/b[height<=720]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "socket_timeout": 30,        # hängende Verbindungen nach 30s abbrechen
        "fragment_retries": 3,
        # HLS-Segmente (Twitch-VOD) parallel laden -> in der Cloud drastisch schneller.
        "concurrent_fragment_downloads": 8,
        # Cookies (falls in .env konfiguriert) – YouTube blockt Downloads sonst
        # mit "Sign in to confirm you're not a bot".
        **ytdlp_cookie_opts(),
    }
    if start_sec is not None and dur_sec:
        from yt_dlp.utils import download_range_func  # lazy

        start = max(0.0, float(start_sec))
        ydl_opts["download_ranges"] = download_range_func(None, [(start, start + float(dur_sec))])
        # nur das Fenster laden (kein voller VOD-Download); Stream-Copy an Keyframes
        # = schnell. Exakte Fenstergrenze ist egal, da Segmente intern neu geschnitten werden.
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    # tatsächlich geschriebene Datei finden (Endung kann variieren)
    matches = sorted(out_dir.glob(f"{basename}.*"))
    matches = [m for m in matches if m.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    return str(matches[0]) if matches else None
