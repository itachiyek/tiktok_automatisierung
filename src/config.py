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
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_LLM_PROVIDER = "auto"  # auto | openai | anthropic


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

    # --- Quellen-Shortcuts ---
    @property
    def twitch(self) -> dict:
        return self.sources.get("twitch", {}) or {}

    @property
    def youtube(self) -> dict:
        return self.sources.get("youtube", {}) or {}

    def tiktok_access_token(self) -> Optional[str]:
        return os.environ.get(f"TIKTOK_ACCESS_TOKEN_{self.id.upper()}")

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


def ytdlp_cookie_opts() -> dict:
    """yt-dlp-Optionen (Python-API) für Cookies aus Browser/Datei.

    YouTube verlangt für Downloads inzwischen Login-Cookies ("Sign in to
    confirm you're not a bot"). Steuerung via .env:
      YTDLP_COOKIES_BROWSER=chrome|edge|firefox|brave  (optional :profil)
      YTDLP_COOKIES_FILE=C:\\pfad\\cookies.txt
    Leeres Dict = keine Cookies (dann nur Auflisten möglich, kein Download).
    """
    file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if file:
        return {"cookiefile": file}
    browser = os.environ.get("YTDLP_COOKIES_BROWSER", "").strip()
    if browser:
        name, _, profile = browser.partition(":")
        spec = (name.lower(), profile or None, None, None)
        return {"cookiesfrombrowser": spec}
    return {}


def ytdlp_cookie_cli() -> list[str]:
    """Wie ytdlp_cookie_opts(), aber als CLI-Argumente für den yt-dlp-Aufruf."""
    file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if file:
        return ["--cookies", file]
    browser = os.environ.get("YTDLP_COOKIES_BROWSER", "").strip()
    if browser:
        return ["--cookies-from-browser", browser.lower()]
    return []


def anthropic_api_key() -> Optional[str]:
    return os.environ.get("ANTHROPIC_API_KEY")


def anthropic_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)


def openai_api_key() -> Optional[str]:
    return os.environ.get("OPENAI_API_KEY")


def openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


def llm_provider() -> str:
    """Welcher LLM-Anbieter erzeugt Captions/Hashtags?

    'auto' (Default): OpenAI bevorzugt, wenn OPENAI_API_KEY gesetzt ist,
    sonst Anthropic. Mit LLM_PROVIDER=openai|anthropic explizit erzwingbar.
    """
    return os.environ.get("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower()


def active_llm_provider() -> Optional[str]:
    """Tatsächlich nutzbarer Anbieter (berücksichtigt vorhandene Keys). None = kein Key."""
    pref = llm_provider()
    if pref == "openai":
        return "openai" if openai_api_key() else None
    if pref == "anthropic":
        return "anthropic" if anthropic_api_key() else None
    # auto
    if openai_api_key():
        return "openai"
    if anthropic_api_key():
        return "anthropic"
    return None


def tiktok_credentials() -> tuple[Optional[str], Optional[str]]:
    return os.environ.get("TIKTOK_CLIENT_KEY"), os.environ.get("TIKTOK_CLIENT_SECRET")


def tiktok_redirect_uri() -> str:
    return os.environ.get("TIKTOK_REDIRECT_URI", "http://localhost:8080/callback")


def ensure_dirs() -> None:
    for d in (DATA_DIR, DOWNLOAD_DIR, RENDER_DIR):
        d.mkdir(parents=True, exist_ok=True)
