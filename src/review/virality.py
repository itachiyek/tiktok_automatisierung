"""Viralitäts-Gate: Kandidaten-Segmente transkribieren (OpenAI) und scoren.

Ablauf pro Segment: Audio extrahieren (ffmpeg) -> Transkription (OpenAI) ->
LLM bewertet Viral-Potenzial 0-10 (Hook, Emotion, Payoff, Zitierfähigkeit).
Nur Segmente >= min_score werden gerendert/gepostet.

Fail-open: ohne OPENAI_API_KEY oder bei API-Fehlern wird NICHT blockiert,
sondern die Energie-Reihenfolge beibehalten (score=None) – die Pipeline darf
nie an der Bewertung sterben.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from ..config import openai_api_key, openai_model
from ..models import Segment

DEFAULT_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
MIN_WORDS = 25  # weniger gesprochene Wörter -> kaum Story, gar nicht erst scoren

SCORE_PROMPT = """Du bist Kurator eines deutschen TikTok-Clip-Kanals. Bewerte das Viral-Potenzial
dieses Transkript-Ausschnitts aus einem Stream von {name} (Nische: {niche}).

Kriterien (TikTok, deutsches Publikum):
- Hook: Fesselt der Anfang in den ersten 3 Sekunden?
- Emotion: Lachen, Eskalation, Überraschung, Wut, Freude?
- Story/Payoff: Abgeschlossener Moment mit Höhepunkt?
- Zitierfähigkeit: Sprüche/Momente, die man teilen will?
Reine Gameplay-Beschreibung, Gemurmel, Pausen, Werbung/Danksagungen = niedriger Score.

Transkript ({dur:.0f} Sekunden):
{transcript}

Antworte NUR als JSON: {{"score": <0-10>, "reason": "<1 kurzer Satz>"}}"""

# (Segment, Transkript, Score oder None)
Ranked = Tuple[Segment, str, Optional[float]]


def _extract_audio(src: str, seg: Segment, out_path: str) -> None:
    cmd = [
        "ffmpeg", "-y", "-ss", str(seg.start), "-to", str(seg.end), "-i", src,
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", "-loglevel", "error", out_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Audio-Extraktion fehlgeschlagen: {proc.stderr[-300:]}")


def _transcribe(client, path: str, language: str) -> str:
    model = os.environ.get("OPENAI_TRANSCRIBE_MODEL", DEFAULT_TRANSCRIBE_MODEL)
    with open(path, "rb") as f:
        resp = client.audio.transcriptions.create(model=model, file=f, language=language)
    return (getattr(resp, "text", "") or "").strip()


def _score(client, transcript: str, name: str, niche: str, dur: float) -> Tuple[float, str]:
    prompt = SCORE_PROMPT.format(name=name, niche=niche, transcript=transcript[:3000], dur=dur)
    resp = client.chat.completions.create(
        model=openai_model(),
        max_tokens=150,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.choices[0].message.content or "{}"
    data = json.loads(text[text.find("{"): text.rfind("}") + 1] or "{}")
    return float(data.get("score", 0.0)), str(data.get("reason", ""))


def rank(
    local_path: str,
    segments: List[Segment],
    name: str,
    niche: str,
    language: str,
    max_keep: int,
    min_score: float,
) -> List[Ranked]:
    """Bewertet die Kandidaten und liefert die besten max_keep über min_score.

    Ohne OpenAI-Key: Gate inaktiv -> lauteste Segmente (score=None, Transkript leer).
    """
    if not segments:
        return []
    key = openai_api_key()
    if not key:
        print("[virality] kein OPENAI_API_KEY – Gate inaktiv, nehme energiereichste Segmente.", flush=True)
        ordered = sorted(segments, key=lambda s: s.score, reverse=True)
        return [(s, "", None) for s in ordered[:max_keep]]

    from openai import OpenAI  # lazy

    client = OpenAI(api_key=key)
    results: List[Ranked] = []
    for seg in segments:
        transcript, score, reason = "", None, ""
        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio = str(Path(tmp) / "seg.mp3")
                _extract_audio(local_path, seg, audio)
                transcript = _transcribe(client, audio, language)
            if len(transcript.split()) < MIN_WORDS:
                score, reason = 1.0, f"kaum Sprache ({len(transcript.split())} Wörter)"
            else:
                score, reason = _score(client, transcript, name, niche, seg.duration)
        except Exception as exc:  # noqa - fail-open, Segment bleibt mit score=None im Rennen
            print(f"[virality] Fehler bei {seg.start:.0f}-{seg.end:.0f}s: {exc}", flush=True)
        results.append((seg, transcript, score))
        shown = f"{score:.1f}" if score is not None else "n/a"
        print(f"[virality] {seg.start:.0f}-{seg.end:.0f}s -> Score {shown} {('– ' + reason) if reason else ''}",
              flush=True)

    # score=None (API-Fehler) zählt als bestanden, sonst harte Schwelle.
    passed = [r for r in results if r[2] is None or r[2] >= min_score]
    passed.sort(key=lambda r: r[2] if r[2] is not None else min_score, reverse=True)
    return passed[:max_keep]
