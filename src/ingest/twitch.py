"""Twitch Helix: vorhandene Community-Clips (= kuratierte Highlights) und VODs abrufen."""
from __future__ import annotations

from typing import Optional

from ..models import SourceItem, TWITCH_CLIP, TWITCH_VOD

HELIX = "https://api.twitch.tv/helix"
OAUTH = "https://id.twitch.tv/oauth2/token"


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str):
        if not client_id or not client_secret:
            raise ValueError("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET fehlen.")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None

    @staticmethod
    def _requests():
        import requests  # lazy

        return requests

    def _auth(self) -> str:
        if self._token:
            return self._token
        r = self._requests().post(
            OAUTH,
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        return {"Client-Id": self.client_id, "Authorization": f"Bearer {self._auth()}"}

    def _get(self, path: str, params: dict) -> dict:
        r = self._requests().get(
            f"{HELIX}/{path}", headers=self._headers(), params=params, timeout=30
        )
        r.raise_for_status()
        return r.json()

    def get_user_id(self, login: str) -> Optional[str]:
        data = self._get("users", {"login": login}).get("data", [])
        return data[0]["id"] if data else None

    def get_clips(
        self, login: str, started_at: Optional[str] = None, limit: int = 20
    ) -> list[SourceItem]:
        """Top-Clips eines Creators. `started_at` als RFC3339 (z. B. letzte 7 Tage)."""
        uid = self.get_user_id(login)
        if not uid:
            return []
        params = {"broadcaster_id": uid, "first": min(limit, 100)}
        if started_at:
            params["started_at"] = started_at
        items = []
        for c in self._get("clips", params).get("data", []):
            items.append(
                SourceItem(
                    creator_id=login,
                    platform=TWITCH_CLIP,
                    source_id=c["id"],
                    title=c.get("title", ""),
                    url=c.get("url", ""),
                    duration_sec=float(c.get("duration", 0) or 0),
                    created_at=c.get("created_at", ""),
                    extra={"view_count": c.get("view_count", 0)},
                )
            )
        return items

    def get_vods(self, login: str, limit: int = 5) -> list[SourceItem]:
        """Archivierte VODs eines Creators (für eigene Highlight-Erkennung)."""
        uid = self.get_user_id(login)
        if not uid:
            return []
        data = self._get(
            "videos", {"user_id": uid, "type": "archive", "first": min(limit, 100)}
        ).get("data", [])
        items = []
        for v in data:
            items.append(
                SourceItem(
                    creator_id=login,
                    platform=TWITCH_VOD,
                    source_id=v["id"],
                    title=v.get("title", ""),
                    url=v.get("url", ""),
                    duration_sec=_parse_twitch_duration(v.get("duration", "0s")),
                    created_at=v.get("created_at", ""),
                )
            )
        return items


def _parse_twitch_duration(s: str) -> float:
    """'1h2m3s' -> Sekunden."""
    total, num = 0.0, ""
    for ch in s:
        if ch.isdigit():
            num += ch
        elif ch in "hms" and num:
            total += int(num) * {"h": 3600, "m": 60, "s": 1}[ch]
            num = ""
    return total
