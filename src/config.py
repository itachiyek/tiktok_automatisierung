"""Konfiguration: lädt creators.yaml + .env und stellt Pfade/Helper bereit."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOWNLOAD_DIR = DATA_DIR / "downloads"
RENDER_DIR = DATA_DIR / "renders"
DB_PATH = DATA_DIR / "clips.db"

DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"


def load_env() -> None:
    """Lädt .env (falls python-dotenv installiert ist)."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(ROOT / ".env")
    except Exception:
        pass


class Creator:
    """Ein Creator-Profil inkl. der globalen Defaults (clip/posting)."""

    def __init__(self, raw: dict, defaults: dict):
        self.raw = raw
        self.id: str = raw["id"]
        self.name: str = raw.get("name", self.id)
        self.consent: bool = bool(raw.get("consent", False))
        self.revenue_share = raw.get("revenue_share")
        self.sources: dict = raw.get("sources", {})
        self.tiktok_account: str = raw.get("tiktok_account", "")
        self.style: dict = raw.get("style", {})
        self.clip: dict = {**defaults.get("clip", {}), **raw.get("clip", {})}
        self.posting: dict = {**defaults.get("posting", {}), **raw.get("posting", {})}
        # Optionale, in Zernio verbundene Account-ID (sonst per @handle aufgelöst).
        self._zernio_account_id: str = raw.get("zernio_account_id", "") or ""

    # --- Quellen-Shortcuts ---
    @property
    def twitch(self) -> dict:
        return self.sources.get("twitch", {}) or {}

    @property
    def youtube(self) -> dict:
        return self.sources.get("youtube", {}) or {}

    def tiktok_access_token(self) -> Optional[str]:
        return os.environ.get(f"TIKTOK_ACCESS_TOKEN_{self.id.upper()}")

    def zernio_account_id(self) -> Optional[str]:
        """Zernio-Account-ID: aus creators.yaml oder Env ZERNIO_ACCOUNT_ID_<ID>."""
        return self._zernio_account_id or os.environ.get(
            f"ZERNIO_ACCOUNT_ID_{self.id.upper()}"
        )

    def uploader(self) -> str:
        """Welcher Upload-Weg: 'zernio' (Standard, wenn Key vorhanden) oder 'tiktok'."""
        configured = (self.posting.get("uploader") or "").lower()
        if configured:
            return configured
        return "zernio" if zernio_api_key() else "tiktok"

    def __repr__(self) -> str:
        return f"<Creator {self.id} consent={self.consent}>"


class Config:
    def __init__(self, creators: list[Creator], defaults: dict):
        self.creators = creators
        self.defaults = defaults

    def get(self, creator_id: str) -> Optional[Creator]:
        return next((c for c in self.creators if c.id == creator_id), None)


def load_config(path: Optional[str] = None) -> Config:
    """Lädt config/creators.yaml (fällt sonst auf den Beispielpfad-Hinweis zurück)."""
    load_env()
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("PyYAML fehlt – `pip install -r requirements.txt`") from exc

    p = Path(path) if path else (ROOT / "config" / "creators.yaml")
    if not p.exists():
        example = ROOT / "config" / "creators.example.yaml"
        if example.exists():
            print(f"[config] {p.name} fehlt – nutze {example.name}. "
                  f"Für den Echtbetrieb:  cp {example} {p}")
            p = example
        else:
            raise FileNotFoundError(f"Weder {p} noch {example} vorhanden.")
    data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    defaults = data.get("defaults", {}) or {}
    creators = [Creator(c, defaults) for c in (data.get("creators", []) or [])]
    return Config(creators, defaults)


# --- Env-Helper für Keys -------------------------------------------------
def twitch_credentials() -> tuple[Optional[str], Optional[str]]:
    return os.environ.get("TWITCH_CLIENT_ID"), os.environ.get("TWITCH_CLIENT_SECRET")


def youtube_api_key() -> Optional[str]:
    return os.environ.get("YOUTUBE_API_KEY")


def anthropic_api_key() -> Optional[str]:
    return os.environ.get("ANTHROPIC_API_KEY")


def anthropic_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)


def tiktok_credentials() -> tuple[Optional[str], Optional[str]]:
    return os.environ.get("TIKTOK_CLIENT_KEY"), os.environ.get("TIKTOK_CLIENT_SECRET")


def zernio_api_key() -> Optional[str]:
    return os.environ.get("ZERNIO_API_KEY")


def zernio_base_url() -> str:
    # Basis inkl. /api; Endpunkte sind /v1/...  -> https://zernio.com/api/v1/...
    return os.environ.get("ZERNIO_BASE_URL", "https://zernio.com/api")


def tiktok_redirect_uri() -> str:
    return os.environ.get("TIKTOK_REDIRECT_URI", "http://localhost:8080/callback")


def ensure_dirs() -> None:
    for d in (DATA_DIR, DOWNLOAD_DIR, RENDER_DIR):
        d.mkdir(parents=True, exist_ok=True)
