"""Zernio Social-Media-API – TikTok-Posting.

Zernio (https://zernio.com) ist eine Unified-Posting-API: übernimmt TikTok-OAuth,
Transcoding, Rate-Limits und Scheduling. Damit umgehen wir den blockierten
Direkt-Upload/Audit-Weg (siehe src/upload/tiktok.py).

Ablauf pro Video:
  1) POST /media/presign  -> uploadUrl (PUT-Ziel) + publicUrl (Referenz im Post)
  2) PUT  uploadUrl       -> Videodatei hochladen (video/mp4)
  3) POST /posts          -> Post anlegen (publishNow oder scheduledFor)

Auth: Header "Authorization: Bearer <ZERNIO_API_KEY>".
"""
from __future__ import annotations

import os
from typing import Optional

BASE = "https://zernio.com/api/v1"


class ZernioError(RuntimeError):
    pass


class ZernioClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ZernioError("Kein ZERNIO_API_KEY gesetzt (.env).")
        self.api_key = api_key

    @staticmethod
    def _requests():
        import requests  # lazy

        return requests

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # --- Konten -----------------------------------------------------------
    def list_accounts(self) -> list[dict]:
        r = self._requests().get(f"{BASE}/accounts", headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json().get("accounts", [])

    def tiktok_account(self, username: Optional[str] = None) -> dict:
        """Liefert das verbundene TikTok-Konto (optional per Username gefiltert)."""
        accts = [a for a in self.list_accounts() if a.get("platform") == "tiktok" and a.get("isActive", True)]
        if username:
            accts = [a for a in accts if _username(a) == username]
        if not accts:
            raise ZernioError("Kein aktives TikTok-Konto in Zernio verbunden.")
        if len(accts) > 1 and not username:
            names = ", ".join(_username(a) for a in accts)
            raise ZernioError(f"Mehrere TikTok-Konten verbunden ({names}) – bitte username angeben.")
        return accts[0]

    # --- Media-Upload -----------------------------------------------------
    def presign(self, filename: str, content_type: str = "video/mp4") -> tuple[str, str]:
        body = {"filename": filename, "contentType": content_type}
        r = self._requests().post(f"{BASE}/media/presign", headers=self._headers(), json=body, timeout=60)
        if r.status_code >= 400:
            raise ZernioError(f"presign fehlgeschlagen: {r.status_code} {r.text[:400]}")
        data = r.json()
        up = data.get("uploadUrl")
        pub = data.get("publicUrl")
        if not up or not pub:
            raise ZernioError(f"presign ohne uploadUrl/publicUrl: {r.text[:400]}")
        return up, pub

    def upload_file(self, upload_url: str, path: str, content_type: str = "video/mp4") -> None:
        with open(path, "rb") as f:
            data = f.read()
        r = self._requests().put(
            upload_url,
            data=data,
            headers={"Content-Type": content_type},
            timeout=600,
        )
        if r.status_code not in (200, 201, 204):
            raise ZernioError(f"Upload fehlgeschlagen: {r.status_code} {r.text[:300]}")

    # --- Post anlegen -----------------------------------------------------
    def create_post(
        self,
        content: str,
        media_url: str,
        account_id: str,
        schedule_iso: Optional[str] = None,
        privacy: str = "PUBLIC_TO_EVERYONE",
        allow_comment: bool = True,
        allow_duet: bool = True,
        allow_stitch: bool = True,
    ) -> dict:
        body = {
            "content": content,
            "mediaItems": [{"type": "video", "url": media_url}],
            "platforms": [{"platform": "tiktok", "accountId": account_id}],
            "tiktokSettings": {
                "privacy_level": privacy,
                "allow_comment": allow_comment,
                "allow_duet": allow_duet,
                "allow_stitch": allow_stitch,
                "content_preview_confirmed": True,
                "express_consent_given": True,
            },
        }
        if schedule_iso:
            body["scheduledFor"] = schedule_iso
            body["publishNow"] = False
        else:
            body["publishNow"] = True
        r = self._requests().post(f"{BASE}/posts", headers=self._headers(), json=body, timeout=120)
        if r.status_code >= 400:
            raise ZernioError(f"Post fehlgeschlagen: {r.status_code} {r.text[:600]}")
        return r.json()

    def get_post(self, post_id: str) -> dict:
        r = self._requests().get(f"{BASE}/posts/{post_id}", headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    def list_posts(self) -> list[dict]:
        r = self._requests().get(f"{BASE}/posts", headers=self._headers(), timeout=30)
        r.raise_for_status()
        d = r.json()
        return d.get("posts") or d.get("data") or (d if isinstance(d, list) else [])

    # --- Convenience ------------------------------------------------------
    def post_video(
        self,
        video_path: str,
        caption: str,
        account_id: str,
        schedule_iso: Optional[str] = None,
        privacy: str = "PUBLIC_TO_EVERYONE",
    ) -> dict:
        filename = os.path.basename(video_path)
        upload_url, public_url = self.presign(filename)
        self.upload_file(upload_url, video_path)
        return self.create_post(
            content=caption,
            media_url=public_url,
            account_id=account_id,
            schedule_iso=schedule_iso,
            privacy=privacy,
        )


def _username(acct: dict) -> str:
    meta = acct.get("metadata") or {}
    prof = meta.get("profileData") or {}
    return prof.get("username") or acct.get("displayName") or acct.get("_id", "")


def api_key_from_env() -> Optional[str]:
    return os.environ.get("ZERNIO_API_KEY")
