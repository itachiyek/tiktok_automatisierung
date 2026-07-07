"""Orchestrator: verbindet Ingest -> Highlight -> Edit -> Metadaten -> Review -> Upload."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from . import db
from .config import (
    Creator,
    DOWNLOAD_DIR,
    RENDER_DIR,
    Config,
    ensure_dirs,
    load_config,
    twitch_credentials,
    youtube_api_key,
)
from .edit import editor
from .highlight.selector import select_segments
from .ingest.downloader import download
from .ingest.twitch import TwitchClient
from .ingest.youtube import YouTubeClient
from .metadata import generator
from .models import Clip, Segment, SourceItem
from .review import quality_gate
from .upload.tiktok import upload_clip


def _log(msg: str) -> None:
    print(f"[pipeline] {msg}", flush=True)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


# Füllwörter, auf denen ein Kurztitel nicht enden darf (sonst "…UND").
_STOP = {
    "und", "oder", "aber", "mit", "bei", "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einen", "einem", "einer", "im", "in", "am", "an", "auf", "aus",
    "für", "zu", "zum", "zur", "von", "vom", "&", "the", "a", "and", "with", "of",
    "to", "my", "is", "vs", "x",
}


def _short_hook(title: str, max_words: int = 5, max_chars: int = 34) -> str:
    """Sinnvolle 3–5-Wort-Kurzbeschreibung für oben im Clip.

    - alles nach dem ersten '|' abschneiden (dort steht oft Twitch-Command-Spam)
    - Chat-Befehle (!x/#x/@x) und Spam-Wörter ("WWWWWW", "?????") raus
    - nie auf einem Füllwort enden ("…UND")
    """
    head = generator._SPAM_RUN_RE.sub(" ", (title or "").split("|")[0])
    # Am ersten Satzende-Zeichen abschneiden, wenn dort schon ein sinnvoller
    # Teil steht (z. B. "Die beste Crew der Welt! SAND …" -> "Die beste Crew der Welt").
    first = re.split(r"[!?.:]", head)[0].strip()
    if len(first.split()) >= 3:
        head = first
    words = [
        w for w in re.split(r"\s+", head)
        if w and not w.startswith(("!", "#", "@")) and not generator._is_spam_word(w)
    ]
    words = words[:max_words]
    while words and words[-1].lower().strip(".,!?:;-") in _STOP:
        words.pop()
    hook = " ".join(words).strip(" -–—|:.,")
    if len(hook) > max_chars:
        hook = hook[:max_chars].rsplit(" ", 1)[0]
        while hook and hook.rsplit(" ", 1)[-1].lower() in _STOP:
            hook = hook.rsplit(" ", 1)[0] if " " in hook else ""
    return hook


def _rfc3339_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def gather_sources(
    creator: Creator,
    include_vods: bool,
    include_youtube: bool,
    limit: int,
    include_clips: bool = True,
) -> List[SourceItem]:
    sources: List[SourceItem] = []
    tw = creator.twitch
    if tw.get("login"):
        cid, csec = twitch_credentials()
        try:
            client = TwitchClient(cid or "", csec or "")
            if include_clips and tw.get("pull_existing_clips", True):
                sources += client.get_clips(
                    tw["login"], started_at=_rfc3339_days_ago(7), limit=limit
                )
            if include_vods and tw.get("pull_vods"):
                sources += client.get_vods(tw["login"], limit=limit)
        except Exception as exc:
            _log(f"Twitch-Ingest fehlgeschlagen ({creator.id}): {exc}")

    if include_youtube and creator.youtube.get("channel_id"):
        try:
            yt = YouTubeClient(youtube_api_key() or "")
            sources += yt.get_recent_uploads(creator.youtube["channel_id"], limit=limit)
        except Exception as exc:
            _log(f"YouTube-Ingest fehlgeschlagen ({creator.id}): {exc}")
    return sources


def process_source(
    conn, creator: Creator, source: SourceItem, auto_upload: bool
) -> List[Clip]:
    if db.is_processed(conn, source.key):
        return []
    ensure_dirs()
    created: List[Clip] = []

    name = _safe(source.key)
    win = float(creator.clip.get("vod_window_sec", 720))
    win_start = float(creator.clip.get("vod_window_start_sec", 1800))
    window_threshold = float(creator.clip.get("window_if_longer_than_sec", 2700))
    # Sehr lange Quellen (z. B. mehrstündige Twitch-VODs) nur als Fenster laden,
    # statt mehrerer GB. Kürzere (YouTube-Uploads) komplett -> bessere Auswahl.
    needs_window = (not source.is_pre_clipped) and source.duration_sec > window_threshold
    if needs_window:
        start = min(win_start, max(0.0, source.duration_sec - win))
        _log(f"Langes Video: lade {win/60:.0f}-min-Fenster ab {start/60:.0f} min …")
        local = download(source.url, DOWNLOAD_DIR, name, start_sec=start, dur_sec=win)
    else:
        local = download(source.url, DOWNLOAD_DIR, name)
    if not local:
        _log(f"Download fehlgeschlagen: {source.url}")
        db.mark_processed(conn, source.key, creator.id)
        return []

    segments = select_segments(source, local, creator.clip)
    credit = f"Credit: {creator.name}"

    for i, seg in enumerate(segments):
        try:
            basename = _safe(f"{source.key}_{i}")
            meta = generator.generate(creator.style, creator.name, source)
            # LLM-Hook bevorzugen (vollständiger Satz); sonst Kurz-Hook aus dem Titel.
            top_title = meta.hook or _short_hook(source.title)
            final = editor.make_clip(
                local, seg, creator.clip, credit, str(RENDER_DIR),
                basename, language=creator.style.get("language", "de"),
                top_title=top_title,
            )
            clip = Clip(
                creator_id=creator.id, source_key=source.key, segment=seg,
                path=final, meta=meta,
            )
            ok, reason = quality_gate.check(conn, clip, creator.clip)
            if not ok:
                _log(f"Clip verworfen ({reason}): {basename}")
                continue
            clip.status = quality_gate.decide_status(creator.clip)
            db.save_clip(conn, clip)
            created.append(clip)
            # Fürs manuelle Posten: Caption + Hashtags als .txt neben den Clip legen.
            try:
                Path(final).with_suffix(".txt").write_text(meta.tiktok_caption(), encoding="utf-8")
            except Exception:
                pass
            _log(f"Clip erstellt #{clip.id} [{clip.status}]: {final}")

            token = creator.tiktok_access_token()
            if auto_upload and clip.status == "approved" and token and clip.id:
                _upload(conn, creator, clip, token)
        except Exception as exc:
            _log(f"Edit/Meta fehlgeschlagen ({source.key} seg {i}): {exc}")

    db.mark_processed(conn, source.key, creator.id)
    return created


def _upload(conn, creator: Creator, clip: Clip, token: str) -> None:
    privacy = creator.posting.get("privacy_level", "SELF_ONLY")
    try:
        caption = clip.meta.tiktok_caption() if clip.meta else ""
        pid = upload_clip(token, clip.path, caption, privacy=privacy)
        db.update_status(conn, clip.id, "uploaded", tiktok_id=pid)
        _log(f"Hochgeladen #{clip.id} -> publish_id={pid} (privacy={privacy})")
    except Exception as exc:
        db.update_status(conn, clip.id, "failed")
        _log(f"Upload fehlgeschlagen #{clip.id}: {exc}")


def run(
    creator_id: Optional[str] = None,
    dry_run: bool = False,
    limit: int = 3,
    include_vods: bool = False,
    include_youtube: bool = False,
    auto_upload: bool = False,
    include_clips: bool = True,
    config: Optional[Config] = None,
) -> List[Clip]:
    cfg = config or load_config()
    conn = db.init_db()
    creators = [cfg.get(creator_id)] if creator_id else cfg.creators
    creators = [c for c in creators if c]
    if not creators:
        _log("Keine passenden Creator in der Config gefunden.")
        return []

    all_clips: List[Clip] = []
    for creator in creators:
        if not creator.consent:
            _log(f"Übersprungen (keine Einwilligung): {creator.id}")
            continue
        _log(f"=== {creator.name} ({creator.id}) ===")
        sources = gather_sources(creator, include_vods, include_youtube, limit, include_clips)
        _log(f"{len(sources)} Quelle(n) gefunden.")

        if dry_run:
            for s in sources[:limit]:
                _log(f"  [dry-run] würde verarbeiten: {s.platform} | {s.title!r} | {s.url}")
            continue

        for source in sources[:limit]:
            all_clips += process_source(conn, creator, source, auto_upload)

    _log(f"Fertig. {len(all_clips)} Clip(s) erzeugt.")
    return all_clips


def upload_approved(creator_id: Optional[str] = None, public: bool = False) -> int:
    """Lädt alle Clips mit Status 'approved' hoch (z. B. nach manueller Freigabe)."""
    cfg = load_config()
    conn = db.init_db()
    count = 0
    for clip in db.list_clips(conn, status="approved", creator_id=creator_id):
        creator = cfg.get(clip.creator_id)
        if not creator:
            continue
        token = creator.tiktok_access_token()
        if not token:
            _log(f"Kein TikTok-Token für {creator.id} – #{clip.id} übersprungen.")
            continue
        if public:
            creator.posting["privacy_level"] = "PUBLIC_TO_EVERYONE"
        _upload(conn, creator, clip, token)
        count += 1
    return count
