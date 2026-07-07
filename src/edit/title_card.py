"""Titel-Karte für den Obertitel: weiße, abgerundete Box mit schwarzem Text.

Wird als transparentes PNG gerendert und in editor.burn() per ffmpeg-Overlay
über das Video gelegt (ASS/BorderStyle=3 kann keine runden Ecken).
"""
from __future__ import annotations

from pathlib import Path

VIDEO_W = 1080          # Zielbreite des 9:16-Videos
MAX_TEXT_W = 860        # max. Textbreite -> Box bleibt sicher im Bild
FONT_SIZE = 74
PAD_X, PAD_Y = 44, 30   # Innenabstand der Box
RADIUS = 34             # Eckenradius
LINE_GAP = 12
MAX_LINES = 3

# Fett bevorzugt; Liberation Sans liegt auf dem CI-Runner (fonts-liberation).
_FONT_CANDIDATES = [
    "arialbd.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_font(size: int):
    from PIL import ImageFont  # lazy

    for cand in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default(size)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if cur and draw.textlength(cand, font=font) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines[:MAX_LINES]


def render_title_card(text: str, out_path: str) -> str:
    """Rendert den Titel als PNG (Box passt sich dem Text an). Gibt out_path zurück."""
    from PIL import Image, ImageDraw  # lazy

    text = " ".join((text or "").split())
    font = _load_font(FONT_SIZE)

    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    lines = _wrap(probe, text, font, MAX_TEXT_W)
    if not lines:
        raise ValueError("leerer Titel")

    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    text_w = max(int(probe.textlength(ln, font=font)) for ln in lines)
    box_w = min(VIDEO_W - 40, text_w + 2 * PAD_X)
    box_h = len(lines) * line_h + (len(lines) - 1) * LINE_GAP + 2 * PAD_Y

    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, box_w - 1, box_h - 1], radius=RADIUS, fill=(255, 255, 255, 255))
    y = PAD_Y
    for ln in lines:
        w = draw.textlength(ln, font=font)
        draw.text(((box_w - w) / 2, y), ln, font=font, fill=(0, 0, 0, 255))
        y += line_h + LINE_GAP

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
