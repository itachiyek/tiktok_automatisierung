"""Wählt aus einem SourceItem die zu schneidenden Segmente."""
from __future__ import annotations

from typing import List

from ..models import Segment, SourceItem
from .audio_energy import compute_energy_windows, pick_segments


def select_segments(source: SourceItem, local_path: str, clip_cfg: dict) -> List[Segment]:
    """Twitch-Clips sind bereits Highlights -> ganzer Clip.
    Volle VODs/Uploads -> Audio-Energie-Erkennung."""
    target = float(clip_cfg.get("min_duration_sec", 61)) + 4.0
    max_clips = int(clip_cfg.get("max_clips_per_source", 3))

    if source.is_pre_clipped:
        end = source.duration_sec if source.duration_sec > 0 else target
        return [Segment(start=0.0, end=round(end, 2), score=1.0)]

    energies = compute_energy_windows(local_path, window_sec=1.0)
    return pick_segments(
        energies,
        window_sec=1.0,
        target_len=target,
        max_clips=max_clips,
        min_gap_sec=float(clip_cfg.get("min_gap_sec", 45)),
    )
