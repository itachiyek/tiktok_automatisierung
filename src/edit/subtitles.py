"""Untertitel via faster-whisper -> ASS (gebrannt im TikTok-Stil)."""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

# (start, end, text)
TranscriptSegment = Tuple[float, float, str]


def transcribe(path: str, language: str = "de", model_size: str = "") -> List[TranscriptSegment]:
    import os

    from faster_whisper import WhisperModel  # lazy

    # Modellgröße via ENV steuerbar (CI nutzt "base" = kleiner/schneller als "small").
    model_size = model_size or os.environ.get("WHISPER_MODEL_SIZE", "small")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(path, language=language, vad_filter=True)
    return [(float(s.start), float(s.end), s.text.strip()) for s in segments if s.text.strip()]


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


# WrapStyle 0 = automatischer, ausgewogener Zeilenumbruch (kein Überlaufen).
# Große, aber nicht zu breite Schrift; große Seitenränder halten Text sicher im 1080px-Bild.
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,Arial,60,&H00FFFFFF,&H00000000,&H64000000,-1,0,1,5,2,2,90,90,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Max. Zeichen pro Untertitel-Event -> passt in <=2 Zeilen bei dieser Schrift/Breite.
MAX_SUB_CHARS = 42


def _chunk(start: float, end: float, text: str, max_chars: int = MAX_SUB_CHARS) -> List[TranscriptSegment]:
    """Zerlegt ein (evtl. langes) Segment in kurze Häppchen mit anteiliger Zeit."""
    words = text.split()
    if not words:
        return []
    groups: list[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            groups.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        groups.append(cur)

    total = sum(len(g) for g in groups) or 1
    span = max(0.0, end - start)
    out: List[TranscriptSegment] = []
    t = start
    for g in groups:
        seg_end = min(end, t + span * (len(g) / total))
        if seg_end <= t:  # Mini-Sicherung gegen Null-Längen
            seg_end = min(end, t + 0.4)
        out.append((t, seg_end, g))
        t = seg_end
    return out


# Kurzer Titel OBEN im Clip (Alignment 8 = oben-mittig): weißer Kasten mit
# schwarzem Text. Nur Fallback, wenn Pillow fehlt – der normale Weg ist die
# PNG-Titel-Karte mit runden Ecken (edit/title_card.py).
# BorderStyle 3 = Kasten, MarginV = Abstand von oben.
TITLE_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Top,Arial,74,&H00000000,&H00FFFFFF,&H00FFFFFF,-1,0,3,10,0,8,70,70,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_title_ass(text: str, out_path: str, duration: float = 60.0, margin_v: int = 260) -> str:
    """Ein kurzer Titel, der die ganze Clip-Dauer oben eingeblendet ist.

    margin_v = Abstand von oben; im Split-Layout klein, damit das Gesicht
    darunter frei bleibt.
    """
    safe = " ".join((text or "").split()).replace("{", "(").replace("}", ")").replace("\\", "/")
    body = TITLE_HEADER.format(margin_v=int(margin_v)) + (
        f"Dialogue: 0,{_ass_time(0)},{_ass_time(max(1.0, duration))},Top,,0,0,0,,{safe}\n"
    )
    Path(out_path).write_text(body, encoding="utf-8")
    return out_path


def write_ass(segments: List[TranscriptSegment], out_path: str) -> str:
    lines = [ASS_HEADER]
    for start, end, text in segments:
        for c_start, c_end, c_text in _chunk(start, end, text):
            safe = c_text.replace("\n", " ").replace("{", "(").replace("}", ")")
            lines.append(
                f"Dialogue: 0,{_ass_time(c_start)},{_ass_time(c_end)},Pop,,0,0,0,,{safe}"
            )
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return out_path
