"""Zernio API – TikTok-Upload & Planung (Scheduling).

Zernio (https://zernio.com) veröffentlicht in unserem Namen auf TikTok & Co.
Großer Vorteil: Zernio ist bereits eine von TikTok auditierte App – wir brauchen
KEIN eigenes Content-Posting-API-Audit und können sofort öffentlich planen/posten.

Ablauf für ein Video:
  1) POST /v1/media/presign   -> {uploadUrl, publicUrl}     (bis 5 GB)
  2) PUT <Datei> an uploadUrl
  3) POST /v1/posts           mit mediaItems=[{type:"video", url:publicUrl}]
     - scheduledFor=<ISO>  -> geplant (Planung)
     - publishNow=true     -> sofort veröffentlichen
     - isDraft=true        -> als Entwurf ablegen

Auth: Header  Authorization: Bearer <ZERNIO_API_KEY>
Basis-URL: https://zernio.com/api   (Endpunkte /v1/...)
"""
from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

DEFAULT_BASE = "https://zernio.com/api"
# Bis 4 MB direkter Multipart-Upload, darüber presign (bis 5 GB).
DIRECT_MAX_BYTES = 4 * 1024 * 1024


class ZernioError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Reine Helfer (ohne Netz) – gut testbar
# --------------------------------------------------------------------------- #
def _to_iso(when: Union[str, datetime, None]) -> Optional[str]:
    if when is None:
        return None
    if isinstance(when, str):
        return when
    return when.isoformat()


def match_account(accounts: List[dict], username: Optional[str]) -> Optional[str]:
    """Findet die Account-_id anhand des @handles (case-insensitiv, ohne @).

    Bei genau einem Konto wird dieses zurückgegeben, auch ohne Handle-Treffer.
    """
    if not accounts:
        return None
    if username:
        want = username.lstrip("@").strip().lower()
        for a in accounts:
            have = str(a.get("username", "")).lstrip("@").strip().lower()
            if have and have == want:
                return a.get("_id") or a.get("id")
    if len(accounts) == 1:
        return accounts[0].get("_id") or accounts[0].get("id")
    return None


def build_tiktok_post_body(
    account_id: str,
    caption: str,
    media_url: str,
    *,
    when: Union[str, datetime, None] = None,
    publish_now: bool = False,
    is_draft: bool = False,
    privacy_level: str = "PUBLIC_TO_EVERYONE",
    allow_comment: bool = True,
    allow_duet: bool = True,
    allow_stitch: bool = True,
    timezone: str = "UTC",
    extra_tiktok_settings: Optional[dict] = None,
) -> Dict[str, Any]:
    """Baut den JSON-Body für POST /v1/posts (TikTok, ein Video)."""
    tiktok_settings: Dict[str, Any] = {
        "privacyLevel": privacy_level,
        "allowComment": allow_comment,
        # allowDuet/allowStitch sind für Video-Posts erforderlich.
        "allowDuet": allow_duet,
        "allowStitch": allow_stitch,
    }
    if extra_tiktok_settings:
        tiktok_settings.update(extra_tiktok_settings)

    body: Dict[str, Any] = {
        "content": caption or "",
        "platforms": [{"platform": "tiktok", "accountId": account_id}],
        "mediaItems": [{"type": "video", "url": media_url}],
        "tiktokSettings": tiktok_settings,
        "timezone": timezone,
    }
    if publish_now:
        body["publishNow"] = True
    elif is_draft:
        body["isDraft"] = True
    elif when is not None:
        body["scheduledFor"] = _to_iso(when)
    else:
        # Kein Zeitpunkt/Modus -> sofort veröffentlichen (sichere Vorgabe).
        body["publishNow"] = True
    return body


def _guess_content_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "video/mp4"


# --------------------------------------------------------------------------- #
# HTTP-Client
# --------------------------------------------------------------------------- #
class ZernioClient:
    def __init__(self, api_key: str, base_url: Optional[str] = None, timeout: float = 60.0):
        if not api_key:
            raise ZernioError("ZERNIO_API_KEY fehlt (in .env eintragen).")
        self.api_key = api_key
        self.base = (base_url or DEFAULT_BASE).rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _requests():
        import requests  # lazy

        return requests

    def _headers(self, json: bool = True) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if json:
            h["Content-Type"] = "application/json"
        return h

    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    # --- Accounts --------------------------------------------------------- #
    def list_accounts(self, platform: Optional[str] = None) -> List[dict]:
        params = {"platform": platform} if platform else None
        r = self._requests().get(
            self._url("/v1/accounts"), headers=self._headers(), params=params, timeout=self.timeout
        )
        r.raise_for_status()
        return r.json().get("accounts", []) or []

    def resolve_account_id(
        self,
        platform: str,
        username: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> str:
        if account_id:
            return account_id
        accounts = self.list_accounts(platform=platform)
        if not accounts:
            raise ZernioError(
                f"Keine {platform}-Konten in Zernio verbunden. "
                f"Konto zuerst unter https://zernio.com verbinden."
            )
        resolved = match_account(accounts, username)
        if resolved:
            return resolved
        candidates = ", ".join(
            f"{a.get('username', '?')}={a.get('_id') or a.get('id')}" for a in accounts
        )
        raise ZernioError(
            f"{platform}-Konto nicht eindeutig – setze zernio_account_id in creators.yaml. "
            f"Kandidaten: {candidates}"
        )

    # --- Media ------------------------------------------------------------ #
    def _presign(self, filename: str, content_type: str, size: int) -> dict:
        r = self._requests().post(
            self._url("/v1/media/presign"),
            headers=self._headers(),
            json={"filename": filename, "contentType": content_type, "size": size},
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise ZernioError(f"presign fehlgeschlagen: {r.status_code} {r.text[:300]}")
        return r.json()

    def _put_file(self, upload_url: str, path: str, content_type: str) -> None:
        with open(path, "rb") as f:
            r = self._requests().put(
                upload_url,
                data=f,
                headers={"Content-Type": content_type},
                timeout=self.timeout * 10,
            )
        if r.status_code not in (200, 201, 204):
            raise ZernioError(f"Datei-Upload (PUT) fehlgeschlagen: {r.status_code} {r.text[:300]}")

    def _direct_upload(self, path: str, content_type: str) -> str:
        p = Path(path)
        with open(path, "rb") as f:
            r = self._requests().post(
                self._url("/v1/media"),
                headers=self._headers(json=False),
                files={"files": (p.name, f, content_type)},
                timeout=self.timeout * 10,
            )
        if r.status_code >= 400:
            raise ZernioError(f"media-Upload fehlgeschlagen: {r.status_code} {r.text[:300]}")
        files = r.json().get("files") or []
        if not files or not files[0].get("url"):
            raise ZernioError(f"media-Upload ohne URL: {r.text[:300]}")
        return files[0]["url"]

    def upload_video(self, path: str, content_type: Optional[str] = None) -> str:
        """Lädt ein Video hoch und gibt die öffentliche URL zurück.

        <=4 MB: direkter Upload; größer: presign + PUT (bis 5 GB).
        """
        p = Path(path)
        if not p.exists():
            raise ZernioError(f"Videodatei fehlt: {path}")
        ctype = content_type or _guess_content_type(path)
        size = p.stat().st_size
        if size <= DIRECT_MAX_BYTES:
            return self._direct_upload(path, ctype)
        pre = self._presign(p.name, ctype, size)
        upload_url = pre.get("uploadUrl")
        public_url = pre.get("publicUrl")
        if not upload_url or not public_url:
            raise ZernioError(f"presign ohne uploadUrl/publicUrl: {pre}")
        self._put_file(upload_url, path, ctype)
        return public_url

    # --- Posts ------------------------------------------------------------ #
    def create_tiktok_post(
        self,
        account_id: str,
        caption: str,
        media_url: str,
        *,
        when: Union[str, datetime, None] = None,
        publish_now: bool = False,
        is_draft: bool = False,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        timezone: str = "UTC",
        extra_tiktok_settings: Optional[dict] = None,
    ) -> str:
        """Erstellt/plant einen TikTok-Post. Rückgabe: Zernio-Post-ID."""
        body = build_tiktok_post_body(
            account_id,
            caption,
            media_url,
            when=when,
            publish_now=publish_now,
            is_draft=is_draft,
            privacy_level=privacy_level,
            timezone=timezone,
            extra_tiktok_settings=extra_tiktok_settings,
        )
        r = self._requests().post(
            self._url("/v1/posts"), headers=self._headers(), json=body, timeout=self.timeout
        )
        if r.status_code >= 400:
            raise ZernioError(f"post create fehlgeschlagen: {r.status_code} {r.text[:400]}")
        data = r.json() or {}
        post = data.get("post") or data.get("existingPost") or {}
        return post.get("_id") or post.get("id") or data.get("id") or ""

    def publish_video(
        self,
        account_id: str,
        video_path: str,
        caption: str,
        *,
        when: Union[str, datetime, None] = None,
        publish_now: bool = False,
        is_draft: bool = False,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        timezone: str = "UTC",
    ) -> str:
        """Komplett-Ablauf: Video hochladen + Post erstellen/planen. Rückgabe: Post-ID."""
        media_url = self.upload_video(video_path)
        return self.create_tiktok_post(
            account_id,
            caption,
            media_url,
            when=when,
            publish_now=publish_now,
            is_draft=is_draft,
            privacy_level=privacy_level,
            timezone=timezone,
        )
