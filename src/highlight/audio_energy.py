"""Audio-Energie als Highlight-Signal: laute Momente = Reaktion/Aufregung/Lachen.

`pick_segments` ist bewusst reine Python-Logik (ohne numpy/ffmpeg), damit testbar.
"""
from __future__ import annotations

import subprocess
from typing import List

from ..models import Segment


def compute_energy_windows(path: str, window_sec: float = 1.0, sr: int = 16000) -> List[float]:
    """RMS-Energie pro Zeitfenster. Nutzt ffmpeg (PCM) + numpy."""
    import numpy as np  # lazy

    cmd = [
        "ffmpeg", "-i", path, "-ac", "1", "-ar", str(sr),
        "-f", "s16le", "-loglevel", "quiet", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return []
    audio = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    win = max(1, int(sr * window_sec))
    n = len(audio) // win
    if n == 0:
        return []
    trimmed = audio[: n * win].reshape(n, win)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1))
    return [float(x) for x in rms]


def pick_segments(
    energies: List[float],
    window_sec: float = 1.0,
    target_len: float = 65.0,
    max_clips: int = 3,
    min_gap_sec: float = 45.0,
) -> List[Segment]:
    """Wählt die energiereichsten, nicht-überlappenden Abschnitte.

    Greedy: höchste Fenster zuerst, jedes als Mittelpunkt eines target_len-Segments,
    Mindestabstand zwischen den Mittelpunkten wird eingehalten.
    """
    if not energies:
        return []
    total = len(energies) * window_sec
    half = target_len / 2.0
    order = sorted(range(len(energies)), key=lambda i: energies[i], reverse=True)

    chosen_centers: list[float] = []
    segments: list[Segment] = []
    for idx in order:
        if len(segments) >= max_clips:
            break
        center = idx * window_sec + window_sec / 2.0
        if any(abs(center - c) < min_gap_sec for c in chosen_centers):
            continue
        start = max(0.0, center - half)
        end = min(total, start + target_len)
        start = max(0.0, end - target_len)  # ans Ende anpassen, Länge halten
        if end - start < min(target_len * 0.6, 30):
            continue
        chosen_centers.append(center)
        segments.append(Segment(start=round(start, 2), end=round(end, 2), score=energies[idx]))

    segments.sort(key=lambda s: s.start)
    return segments
