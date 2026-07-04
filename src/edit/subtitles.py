"""Untertitel via faster-whisper -> ASS (gebrannt im TikTok-Stil).

Die gesprochenen Texte werden standardmäßig OBEN im Video eingeblendet
(`position="top"`). Über `position` lässt sich das umstellen (top|middle|bottom).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

# (start, end, text)
TranscriptSegment = Tuple[float, float, str]

# ASS-Alignment (Numpad-Schema): 8 = oben-mitte, 5 = mitte, 2 = unten-mitte.
_ALIGN = {"top": 8, "middle": 5, "center": 5, "bottom": 2}
# Sinnvoller vertikaler Rand je Position (px bei PlayResY=1920).
# Oben etwas Abstand zur Handy-Statusleiste, unten Abstand zur TikTok-UI.
_DEFAULT_MARGIN = {"top": 230, "middle": 0, "center": 0, "bottom": 300}


def transcribe(path: str, language: str = "de", model_size: str = "small") -> List[TranscriptSegment]:
    from faster_whisper import WhisperModel  # lazy

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


# Alignment + MarginV werden je nach Position eingesetzt (siehe build_header).
ASS_HEADER_TMPL = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,Arial,72,&H00FFFFFF,&H00000000,&H00000000,-1,0,1,6,2,{alignment},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def resolve_alignment(position: str) -> int:
    """Position (top|middle|bottom) -> ASS-Alignment-Wert."""
    return _ALIGN.get((position or "top").lower(), 8)


def build_header(position: str = "top", margin_v: Optional[int] = None) -> str:
    pos = (position or "top").lower()
    align = resolve_alignment(pos)
    mv = _DEFAULT_MARGIN.get(pos, 230) if margin_v is None else int(margin_v)
    return ASS_HEADER_TMPL.format(alignment=align, margin_v=mv)


def write_ass(
    segments: List[TranscriptSegment],
    out_path: str,
    position: str = "top",
    margin_v: Optional[int] = None,
) -> str:
    lines = [build_header(position, margin_v)]
    for start, end, text in segments:
        safe = text.replace("\n", " ").replace("{", "(").replace("}", ")")
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Pop,,0,0,0,,{safe}"
        )
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return out_path
