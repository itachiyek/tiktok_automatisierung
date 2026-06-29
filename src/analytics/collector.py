"""Holt Kennzahlen veröffentlichter Clips über die TikTok Display/Video-API.

Erfordert den Scope video.list für das jeweilige Konto. Minimaler Abruf nach IDs.
"""
from __future__ import annotations

from typing import List

VIDEO_QUERY = "https://open.tiktokapis.com/v2/video/query/"
FIELDS = "id,like_count,comment_count,share_count,view_count"


def fetch_metrics(access_token: str, video_ids: List[str]) -> list[dict]:
    if not access_token or not video_ids:
        return []
    import requests  # lazy

    r = requests.post(
        f"{VIDEO_QUERY}?fields={FIELDS}",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"filters": {"video_ids": video_ids}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("data", {}).get("videos", [])
