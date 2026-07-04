"""Wählt aus einem SourceItem die zu schneidenden Segmente.

Ziel-Länge: 1–2 Minuten (Standard ~90 s). Für TikTok Creator Rewards sollten
Clips > 60 s sein; die Obergrenze von 120 s hält sie zugleich im 1–2-Minuten-Fenster.
"""
from __future__ import annotations

from typing import List

from ..models import Segment, SourceItem
from .audio_energy import compute_energy_windows, pick_segments


def _target_length(clip_cfg: dict) -> float:
    """Ziel-Clip-Länge, geklemmt zwischen min und max (Standard 90 s = 1,5 min)."""
    min_d = float(clip_cfg.get("min_duration_sec", 60))
    max_d = float(clip_cfg.get("max_duration_sec", 120))
    target = float(clip_cfg.get("target_duration_sec", 90))
    return max(min_d, min(target, max_d))


def select_segments(source: SourceItem, local_path: str, clip_cfg: dict) -> List[Segment]:
    """Twitch-Clips sind bereits Highlights -> ganzer Clip (auf max_duration gekürzt).
    Volle VODs/Uploads -> Audio-Energie-Erkennung auf Ziel-Länge (1–2 min)."""
    target = _target_length(clip_cfg)
    max_d = float(clip_cfg.get("max_duration_sec", 120))
    max_clips = int(clip_cfg.get("max_clips_per_source", 3))

    if source.is_pre_clipped:
        dur = source.duration_sec if source.duration_sec > 0 else target
        end = min(dur, max_d)  # lange Community-Clips auf 2 Minuten deckeln
        return [Segment(start=0.0, end=round(end, 2), score=1.0)]

    energies = compute_energy_windows(local_path, window_sec=1.0)
    return pick_segments(
        energies,
        window_sec=1.0,
        target_len=target,
        max_clips=max_clips,
        min_gap_sec=float(clip_cfg.get("min_gap_sec", 60)),
    )
