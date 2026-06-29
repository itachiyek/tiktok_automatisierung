"""Download von Quell-Videos via yt-dlp (Twitch-Clips/VODs, YouTube)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def download(url: str, out_dir, basename: str) -> Optional[str]:
    """Lädt `url` nach out_dir/basename.<ext> und gibt den finalen Pfad zurück."""
    import yt_dlp  # lazy

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "outtmpl": str(out_dir / f"{basename}.%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    # tatsächlich geschriebene Datei finden (Endung kann variieren)
    matches = sorted(out_dir.glob(f"{basename}.*"))
    matches = [m for m in matches if m.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    return str(matches[0]) if matches else None
