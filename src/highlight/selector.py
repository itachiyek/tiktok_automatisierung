"""Wählt aus einem SourceItem die zu schneidenden Segmente."""
from __future__ import annotations

from typing import List

from ..models import Segment, SourceItem
from .audio_energy import compute_energy_windows, pick_segments


def select_segments(
    source: SourceItem, local_path: str, clip_cfg: dict, max_clips: int | None = None
) -> List[Segment]:
    """Twitch-Clips sind bereits Highlights -> ganzer Clip.
    Volle VODs/Uploads -> Audio-Energie-Erkennung.

    Harte Regel: nur Segmente >= 60 s (TikTok Creator Rewards). Pre-Clips, die
    kürzer sind (Twitch-Community-Clips sind max. 60 s!), werden übersprungen.
    max_clips überschreibt die Config (z. B. mehr Kandidaten fürs Viralitäts-Gate).
    """
    min_len = max(60.0, float(clip_cfg.get("min_duration_sec", 61)))
    target = min_len + 4.0
    max_clips = max_clips or int(clip_cfg.get("max_clips_per_source", 3))

    if source.is_pre_clipped:
        dur = source.duration_sec
        if dur and dur < min_len:
            return []  # zu kurz für >=60s -> nicht verwendbar
        end = dur if dur > 0 else target
        return [Segment(start=0.0, end=round(end, 2), score=1.0)]

    energies = compute_energy_windows(local_path, window_sec=1.0)
    return pick_segments(
        energies,
        window_sec=1.0,
        target_len=target,
        max_clips=max_clips,
        # Default = Cliplänge, damit sich Segmente nie überlappen (keine Doppel-Posts).
        min_gap_sec=float(clip_cfg.get("min_gap_sec", target)),
        min_len=min_len,
    )
