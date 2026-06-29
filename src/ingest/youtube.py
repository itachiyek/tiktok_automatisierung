"""YouTube Data API v3: neue Uploads eines Kanals erkennen."""
from __future__ import annotations

import re
from typing import Optional

from ..models import SourceItem, YOUTUBE

API = "https://www.googleapis.com/youtube/v3"


class YouTubeClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY fehlt.")
        self.api_key = api_key

    @staticmethod
    def _requests():
        import requests  # lazy

        return requests

    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "key": self.api_key}
        r = self._requests().get(f"{API}/{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_recent_uploads(
        self, channel_id: str, limit: int = 5, published_after: Optional[str] = None
    ) -> list[SourceItem]:
        if not channel_id or channel_id.startswith("UC_X"):
            return []  # Platzhalter-ID in der Beispiel-Config
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "order": "date",
            "type": "video",
            "maxResults": min(limit, 50),
        }
        if published_after:
            params["publishedAfter"] = published_after
        results = self._get("search", params).get("items", [])
        ids = [r["id"]["videoId"] for r in results if r.get("id", {}).get("videoId")]
        durations = self._durations(ids)
        items = []
        for r in results:
            vid = r.get("id", {}).get("videoId")
            if not vid:
                continue
            sn = r["snippet"]
            items.append(
                SourceItem(
                    creator_id=channel_id,
                    platform=YOUTUBE,
                    source_id=vid,
                    title=sn.get("title", ""),
                    url=f"https://www.youtube.com/watch?v={vid}",
                    duration_sec=durations.get(vid, 0.0),
                    created_at=sn.get("publishedAt", ""),
                )
            )
        return items

    def _durations(self, video_ids: list[str]) -> dict[str, float]:
        if not video_ids:
            return {}
        data = self._get(
            "videos", {"part": "contentDetails", "id": ",".join(video_ids)}
        ).get("items", [])
        return {
            it["id"]: _parse_iso8601_duration(it["contentDetails"]["duration"])
            for it in data
        }


def _parse_iso8601_duration(s: str) -> float:
    """'PT1H2M3S' -> Sekunden."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0.0
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return float(h * 3600 + mi * 60 + se)
