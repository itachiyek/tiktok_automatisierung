"""TikTok Content Posting API – Direct Post (FILE_UPLOAD).

Hinweis: Vor dem Audit erlaubt TikTok nur privacy_level='SELF_ONLY' (privat sichtbar).
Nach erfolgreichem Audit kann 'PUBLIC_TO_EVERYONE' gesetzt werden.
"""
from __future__ import annotations

import os
from typing import Optional

BASE = "https://open.tiktokapis.com/v2"
INIT = f"{BASE}/post/publish/video/init/"
STATUS = f"{BASE}/post/publish/status/fetch/"


class TikTokUploadError(RuntimeError):
    pass


class TikTokClient:
    def __init__(self, access_token: str):
        if not access_token:
            raise TikTokUploadError("Kein TikTok Access-Token (video.publish) gesetzt.")
        self.access_token = access_token

    @staticmethod
    def _requests():
        import requests  # lazy

        return requests

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def direct_post(self, video_path: str, caption: str, privacy: str = "SELF_ONLY") -> str:
        """Lädt ein Video direkt hoch. Rückgabe: publish_id."""
        requests = self._requests()
        size = os.path.getsize(video_path)
        chunk_size = size if size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
        total_chunks = 1 if size <= 64 * 1024 * 1024 else (size + chunk_size - 1) // chunk_size

        init_body = {
            "post_info": {
                "title": caption,
                "privacy_level": privacy,
                "disable_comment": False,
                "disable_duet": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        }
        r = requests.post(INIT, headers=self._headers(), json=init_body, timeout=60)
        r.raise_for_status()
        data = r.json().get("data", {})
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if not publish_id or not upload_url:
            raise TikTokUploadError(f"Init fehlgeschlagen: {r.text[:500]}")

        with open(video_path, "rb") as f:
            for i in range(total_chunks):
                start = i * chunk_size
                chunk = f.read(chunk_size)
                end = start + len(chunk) - 1
                headers = {
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                }
                up = requests.put(upload_url, headers=headers, data=chunk, timeout=300)
                if up.status_code not in (200, 201, 206):
                    raise TikTokUploadError(f"Upload-Chunk {i} fehlgeschlagen: {up.status_code} {up.text[:300]}")
        return publish_id

    def fetch_status(self, publish_id: str) -> dict:
        r = self._requests().post(
            STATUS, headers=self._headers(), json={"publish_id": publish_id}, timeout=30
        )
        r.raise_for_status()
        return r.json().get("data", {})


def upload_clip(access_token: str, video_path: str, caption: str, privacy: str = "SELF_ONLY") -> str:
    client = TikTokClient(access_token)
    return client.direct_post(video_path, caption, privacy=privacy)
