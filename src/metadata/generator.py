"""Erzeugt deutsche Caption + Hashtags via LLM (OpenAI oder Claude).

Anbieter wird über LLM_PROVIDER gesteuert (auto|openai|anthropic). Ohne
nutzbaren API-Key wird ein Template-Fallback verwendet.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from ..config import (
    active_llm_provider,
    anthropic_api_key,
    anthropic_model,
    openai_api_key,
    openai_model,
)
from ..models import ClipMeta, SourceItem

PROMPT = """Du betreibst einen deutschen TikTok-CLIP-Account, der Highlights des Creators {name} postet.
Du bist NICHT {name} selbst – schreibe aus Sicht des Clip-Accounts in der DRITTEN Person ÜBER {name}.
Nische: {niche}
Ton: {tone}
Video-Titel (Quelle): {title}
{transcript_block}
Erstelle Metadaten für EINEN TikTok-Clip von {name}. Auf Deutsch, in der DRITTEN Person über {name}
mit Namen (niemals "ich"/"mein"). Kein Clickbait, kein fremdes Branding.

Stil der caption: SEHR KURZ und locker – 1 knapper Satz (ca. 3-8 Wörter), natürlich, fast beiläufig.
KEIN Cringe, KEINE übertriebenen Hype-Wörter (nicht "krass/Wahnsinn/legendär/episch/crazy"),
höchstens 1 Emoji, oft auch gar keins. Beispiele: "Trymacs bei Deutschland gegen Paraguay" /
"EliasN97 holt seinen neuen Lambo ab".

Antworte AUSSCHLIESSLICH als JSON:
{{"title": "...", "hook": "...", "caption": "...", "hashtags": ["#...", "#..."]}}
- hook: SEHR kurzer, VOLLSTÄNDIGER Titel für oben im Video – 3 bis 5 Wörter, worum es im
  Clip geht. MUSS ein sinnvoller, abgeschlossener Ausdruck sein (NIEMALS mitten im Satz
  abbrechen, nicht auf "und/mit/bei/der" enden). Ohne Hashtags/Emojis. Beispiele:
  "Elquaria bei Red Bull Gamerations" / "Trymacs' bester Round" / "EliasN97 holt den Lambo".
- caption: kurz, 1 Satz, dritte Person über {name}, max. 1 Emoji.
- hashtags: 5-8 Stück, gemischt aus Creator-/Nischen-/Trend-Tags, inkl. #fyp.
"""


def _clean_source_title(title: str) -> str:
    """Twitch-Titel entrümpeln: alles nach dem ersten '|' weg (Command-Spam),
    Chat-Befehle (!x/#x/@x) raus, Ränder trimmen."""
    head = (title or "").split("|")[0]
    words = [w for w in re.split(r"\s+", head) if w and not w.startswith(("!", "#", "@"))]
    return " ".join(words).strip(" -–—|:;,.")


def _build_prompt(creator_style: dict, name: str, source: SourceItem, transcript: Optional[str]) -> str:
    tb = f"Transkript-Auszug: {transcript[:800]}" if transcript else ""
    return PROMPT.format(
        name=name,
        niche=", ".join(creator_style.get("niche", []) or ["entertainment"]),
        tone=creator_style.get("tone", "energiegeladen"),
        title=_clean_source_title(source.title) or "(kein Titel)",
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
    clean = _clean_source_title(source.title)
    caption = f"{name} – das musst du sehen! 😮 {clean}".strip()
    seen, tags = set(), []
    for t in base:
        if t not in seen:
            seen.add(t)
            tags.append(t)
    return ClipMeta(title=clean or f"{name} Highlight", caption=caption, hashtags=tags[:8])


def _meta_from_data(data: dict, name: str, source: SourceItem) -> Optional[ClipMeta]:
    if not data.get("caption"):
        return None
    tags = data.get("hashtags", []) or []
    return ClipMeta(
        title=data.get("title", source.title or name),
        caption=data["caption"],
        hashtags=[t if t.startswith("#") else f"#{t}" for t in tags],
        hook=(data.get("hook") or "").strip(),
    )


def _generate_openai(prompt: str) -> dict:
    from openai import OpenAI  # lazy

    client = OpenAI(api_key=openai_api_key())
    resp = client.chat.completions.create(
        model=openai_model(),
        max_tokens=600,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(resp.choices[0].message.content or "")


def _generate_anthropic(prompt: str) -> dict:
    import anthropic  # lazy

    client = anthropic.Anthropic(api_key=anthropic_api_key())
    resp = client.messages.create(
        model=anthropic_model(),
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(getattr(b, "text", "") for b in resp.content)
    return _parse_json(text)


def generate(creator_style: dict, name: str, source: SourceItem, transcript: Optional[str] = None) -> ClipMeta:
    provider = active_llm_provider()
    if not provider:
        return _fallback(creator_style, name, source)
    prompt = _build_prompt(creator_style, name, source, transcript)
    try:
        data = _generate_openai(prompt) if provider == "openai" else _generate_anthropic(prompt)
        meta = _meta_from_data(data, name, source)
        if meta:
            return meta
    except Exception:
        pass
    return _fallback(creator_style, name, source)
