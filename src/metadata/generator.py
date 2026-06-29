"""Erzeugt deutsche Caption + Hashtags via Claude (Fallback ohne Key: Template)."""
from __future__ import annotations

import json
from typing import Optional

from ..config import anthropic_api_key, anthropic_model
from ..models import ClipMeta, SourceItem

PROMPT = """Du bist Social-Media-Manager für virale deutsche TikTok-Clips.
Creator: {name}
Nische: {niche}
Ton: {tone}
Video-Titel (Quelle): {title}
{transcript_block}
Erstelle Metadaten für EINEN TikTok-Clip dieses Creators. Auf Deutsch, jugendlich,
mit starkem Hook in der ersten Zeile. Keine Clickbait-Lügen, kein fremdes Branding.

Antworte AUSSCHLIESSLICH als JSON:
{{"title": "...", "caption": "...", "hashtags": ["#...", "#..."]}}
- caption: 1-2 Sätze, hooky.
- hashtags: 5-8 Stück, gemischt aus Creator-/Nischen-/Trend-Tags, inkl. #fyp.
"""


def _build_prompt(creator_style: dict, name: str, source: SourceItem, transcript: Optional[str]) -> str:
    tb = f"Transkript-Auszug: {transcript[:800]}" if transcript else ""
    return PROMPT.format(
        name=name,
        niche=", ".join(creator_style.get("niche", []) or ["entertainment"]),
        tone=creator_style.get("tone", "energiegeladen"),
        title=source.title or "(kein Titel)",
        transcript_block=tb,
    )


def _parse_json(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return {}
    return {}


def _fallback(creator_style: dict, name: str, source: SourceItem) -> ClipMeta:
    niche = creator_style.get("niche", []) or ["clips"]
    base = [f"#{name.lower().replace(' ', '')}", "#fyp", "#viral", "#deutschland"]
    base += [f"#{n}" for n in niche]
    caption = f"{name} – das musst du sehen! 😮 {source.title}".strip()
    seen, tags = set(), []
    for t in base:
        if t not in seen:
            seen.add(t)
            tags.append(t)
    return ClipMeta(title=source.title or f"{name} Highlight", caption=caption, hashtags=tags[:8])


def generate(creator_style: dict, name: str, source: SourceItem, transcript: Optional[str] = None) -> ClipMeta:
    key = anthropic_api_key()
    if not key:
        return _fallback(creator_style, name, source)
    try:
        import anthropic  # lazy

        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=anthropic_model(),
            max_tokens=600,
            messages=[{"role": "user", "content": _build_prompt(creator_style, name, source, transcript)}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content)
        data = _parse_json(text)
        if data.get("caption"):
            tags = data.get("hashtags", []) or []
            return ClipMeta(
                title=data.get("title", source.title or name),
                caption=data["caption"],
                hashtags=[t if t.startswith("#") else f"#{t}" for t in tags],
            )
    except Exception:
        pass
    return _fallback(creator_style, name, source)
