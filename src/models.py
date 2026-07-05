"""Gemeinsame Datenstrukturen der Pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Plattform-Typen für SourceItem.platform
TWITCH_CLIP = "twitch_clip"
TWITCH_VOD = "twitch_vod"
YOUTUBE = "youtube"


@dataclass
class SourceItem:
    """Ein Quell-Video (Twitch-Clip/VOD oder YouTube-Upload)."""

    creator_id: str
    platform: str
    source_id: str
    title: str
    url: str
    duration_sec: float = 0.0
    created_at: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.source_id}"

    @property
    def is_pre_clipped(self) -> bool:
        """Twitch-Community-Clips sind bereits fertige Highlights."""
        return self.platform == TWITCH_CLIP


@dataclass
class Segment:
    """Ein ausgewählter Zeitabschnitt innerhalb eines SourceItem."""

    start: float
    end: float
    score: float = 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class ClipMeta:
    title: str
    caption: str
    hashtags: list[str] = field(default_factory=list)
    hook: str = ""  # kurzer, vollständiger 3–5-Wort-Titel für oben im Clip (vom LLM)

    def tiktok_caption(self, max_len: int = 2200) -> str:
        """Caption + Hashtags als ein TikTok-Text."""
        tags = " ".join(h if h.startswith("#") else f"#{h}" for h in self.hashtags)
        text = f"{self.caption}\n\n{tags}".strip()
        return text[:max_len]


@dataclass
class Clip:
    creator_id: str
    source_key: str
    segment: Segment
    path: str = ""
    meta: Optional[ClipMeta] = None
    status: str = "new"  # new | pending_review | approved | uploaded | failed
    tiktok_id: str = ""
    id: Optional[int] = None
