"""Orchestrator: verbindet Ingest -> Highlight -> Edit -> Metadaten -> Review -> Upload.

Zwei Betriebsarten:
  * run(...)       – manuell/halbautomatisch (Cut, optional Upload freigegebener Clips)
  * run_auto(...)  – vollautomatisch für Crons: Cut + Auto-Freigabe + zeitlich
                     gestaffelte Planung via Zernio (siehe scripts/cron_run.sh)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
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
    zernio_api_key,
    zernio_base_url,
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


def _rfc3339_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def gather_sources(
    creator: Creator, include_vods: bool, include_youtube: bool, limit: int
) -> List[SourceItem]:
    sources: List[SourceItem] = []
    tw = creator.twitch
    if tw.get("login"):
        cid, csec = twitch_credentials()
        try:
            client = TwitchClient(cid or "", csec or "")
            if tw.get("pull_existing_clips", True):
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
    conn, creator: Creator, source: SourceItem, auto_approve: bool = False
) -> List[Clip]:
    """Schneidet Clips aus einer Quelle und speichert sie (kein Upload)."""
    if db.is_processed(conn, source.key):
        return []
    ensure_dirs()
    created: List[Clip] = []

    local = download(source.url, DOWNLOAD_DIR, _safe(source.key))
    if not local:
        _log(f"Download fehlgeschlagen: {source.url}")
        db.mark_processed(conn, source.key, creator.id)
        return []

    segments = select_segments(source, local, creator.clip)
    credit = f"Credit: {creator.name}"

    for i, seg in enumerate(segments):
        try:
            basename = _safe(f"{source.key}_{i}")
            final = editor.make_clip(
                local, seg, creator.clip, credit, str(RENDER_DIR),
                basename, language=creator.style.get("language", "de"),
            )
            meta = generator.generate(creator.style, creator.name, source)
            clip = Clip(
                creator_id=creator.id, source_key=source.key, segment=seg,
                path=final, meta=meta,
            )
            ok, reason = quality_gate.check(conn, clip, creator.clip)
            if not ok:
                _log(f"Clip verworfen ({reason}): {basename}")
                continue
            clip.status = quality_gate.decide_status(creator.clip, auto_approve=auto_approve)
            db.save_clip(conn, clip)
            created.append(clip)
            _log(f"Clip erstellt #{clip.id} [{clip.status}]: {final}")
        except Exception as exc:
            _log(f"Edit/Meta fehlgeschlagen ({source.key} seg {i}): {exc}")

    db.mark_processed(conn, source.key, creator.id)
    return created


# --------------------------------------------------------------------------- #
# Upload / Planung
# --------------------------------------------------------------------------- #
def _upload_tiktok(conn, creator: Creator, clip: Clip, token: str) -> None:
    """Legacy-Weg: TikTok Content Posting API direkt (erfordert eigenes Audit)."""
    privacy = creator.posting.get("privacy_level", "SELF_ONLY")
    try:
        caption = clip.meta.tiktok_caption() if clip.meta else ""
        pid = upload_clip(token, clip.path, caption, privacy=privacy)
        db.update_status(conn, clip.id, "uploaded", tiktok_id=pid)
        _log(f"TikTok hochgeladen #{clip.id} -> publish_id={pid} (privacy={privacy})")
    except Exception as exc:
        db.update_status(conn, clip.id, "failed")
        _log(f"TikTok-Upload fehlgeschlagen #{clip.id}: {exc}")


# Rückwärtskompatibler Alias (frühere Signatur _upload(conn, creator, clip, token)).
_upload = _upload_tiktok


def _publish_zernio(
    conn, creator: Creator, clip: Clip, when: Optional[datetime], immediate: bool
) -> None:
    """Upload + Post/Planung via Zernio (kein eigenes TikTok-Audit nötig)."""
    from .upload.zernio import ZernioClient, ZernioError

    key = zernio_api_key()
    if not key:
        _log(f"Kein ZERNIO_API_KEY – #{clip.id} übersprungen.")
        db.update_status(conn, clip.id, "failed")
        return

    posting = creator.posting
    mode = (posting.get("schedule_mode") or "spread").lower()
    privacy = posting.get("privacy_level", "PUBLIC_TO_EVERYONE")
    tz = posting.get("timezone", "UTC")

    publish_now = immediate or (mode == "now" and when is None)
    is_draft = (mode == "draft") and not immediate
    schedule_when = None if (publish_now or is_draft) else when

    try:
        client = ZernioClient(key, zernio_base_url())
        account_id = client.resolve_account_id(
            "tiktok", username=creator.tiktok_account, account_id=creator.zernio_account_id()
        )
        caption = clip.meta.tiktok_caption() if clip.meta else ""
        pid = client.publish_video(
            account_id, clip.path, caption,
            when=schedule_when, publish_now=publish_now, is_draft=is_draft,
            privacy_level=privacy, timezone=tz,
        )
        status = "uploaded" if publish_now else ("draft" if is_draft else "scheduled")
        db.update_status(conn, clip.id, status, tiktok_id=pid)
        when_txt = f" um {schedule_when.isoformat()}" if schedule_when else ""
        _log(f"Zernio {status} #{clip.id} -> post={pid}{when_txt} (privacy={privacy})")
    except ZernioError as exc:
        db.update_status(conn, clip.id, "failed")
        _log(f"Zernio fehlgeschlagen #{clip.id}: {exc}")
    except Exception as exc:
        db.update_status(conn, clip.id, "failed")
        _log(f"Zernio-Upload fehlgeschlagen #{clip.id}: {exc}")


def _publish(
    conn, creator: Creator, clip: Clip, when: Optional[datetime] = None, immediate: bool = False
) -> None:
    """Dispatch: Upload/Planung über den konfigurierten Weg (zernio|tiktok)."""
    uploader = creator.uploader()
    if uploader == "zernio":
        _publish_zernio(conn, creator, clip, when, immediate)
        return
    token = creator.tiktok_access_token()
    if not token:
        _log(f"Kein TikTok-Token für {creator.id} – #{clip.id} übersprungen.")
        db.update_status(conn, clip.id, "failed")
        return
    _upload_tiktok(conn, creator, clip, token)


def schedule_times(
    count: int, first_delay_min: int, spacing_min: int, base: Optional[datetime] = None
) -> List[datetime]:
    """Gestaffelte Veröffentlichungszeiten (reine Funktion, testbar)."""
    start = base or datetime.now(timezone.utc)
    return [start + timedelta(minutes=first_delay_min + i * spacing_min) for i in range(count)]


def _schedule_creator(conn, creator: Creator, clips: List[Clip]) -> int:
    """Plant/veröffentlicht die frisch freigegebenen Clips eines Creators."""
    posting = creator.posting
    mode = (posting.get("schedule_mode") or "spread").lower()
    max_day = int(posting.get("per_account_per_day", 3))
    approved = [c for c in clips if c.status == "approved"][:max_day]
    if not approved:
        return 0

    if mode == "spread":
        times = schedule_times(
            len(approved),
            int(posting.get("first_delay_min", 20)),
            int(posting.get("spacing_min", 180)),
        )
        for clip, when in zip(approved, times):
            _publish(conn, creator, clip, when=when)
    elif mode == "now":
        for clip in approved:
            _publish(conn, creator, clip, immediate=True)
    else:  # draft
        for clip in approved:
            _publish(conn, creator, clip)
    return len(approved)


# --------------------------------------------------------------------------- #
# Läufe
# --------------------------------------------------------------------------- #
def _consenting(creators: List[Creator]) -> List[Creator]:
    out = []
    for c in creators:
        if not c:
            continue
        if not c.consent:
            _log(f"Übersprungen (keine Einwilligung): {c.id}")
            continue
        out.append(c)
    return out


def run(
    creator_id: Optional[str] = None,
    dry_run: bool = False,
    limit: int = 3,
    include_vods: bool = False,
    include_youtube: bool = False,
    auto_upload: bool = False,
    config: Optional[Config] = None,
) -> List[Clip]:
    cfg = config or load_config()
    conn = db.init_db()
    creators = [cfg.get(creator_id)] if creator_id else cfg.creators
    creators = _consenting([c for c in creators if c])
    if not creators:
        _log("Keine passenden Creator (mit Einwilligung) in der Config gefunden.")
        return []

    all_clips: List[Clip] = []
    for creator in creators:
        _log(f"=== {creator.name} ({creator.id}) ===")
        sources = gather_sources(creator, include_vods, include_youtube, limit)
        _log(f"{len(sources)} Quelle(n) gefunden.")

        if dry_run:
            for s in sources[:limit]:
                _log(f"  [dry-run] würde verarbeiten: {s.platform} | {s.title!r} | {s.url}")
            continue

        for source in sources[:limit]:
            created = process_source(conn, creator, source)
            all_clips += created
            if auto_upload:
                for clip in created:
                    if clip.status == "approved":
                        _publish(conn, creator, clip, immediate=True)

    _log(f"Fertig. {len(all_clips)} Clip(s) erzeugt.")
    return all_clips


def run_auto(
    creator_id: Optional[str] = None,
    limit: int = 3,
    include_vods: bool = True,
    include_youtube: bool = False,
    dry_run: bool = False,
    force_now: bool = False,
    config: Optional[Config] = None,
) -> List[Clip]:
    """Vollautomatischer Cron-Lauf: Cut -> Auto-Freigabe -> Planung/Upload via Zernio."""
    cfg = config or load_config()
    conn = db.init_db()
    creators = [cfg.get(creator_id)] if creator_id else cfg.creators
    creators = _consenting([c for c in creators if c])
    if not creators:
        _log("Keine passenden Creator (mit Einwilligung) in der Config gefunden.")
        return []

    all_clips: List[Clip] = []
    for creator in creators:
        _log(f"=== [auto] {creator.name} ({creator.id}) ===")
        sources = gather_sources(creator, include_vods, include_youtube, limit)
        _log(f"{len(sources)} Quelle(n) gefunden.")

        created: List[Clip] = []
        for source in sources[:limit]:
            if dry_run:
                _log(f"  [dry-run] würde verarbeiten: {source.platform} | {source.title!r}")
                continue
            created += process_source(conn, creator, source, auto_approve=True)

        all_clips += created
        if not dry_run and created:
            if force_now:
                for clip in created:
                    if clip.status == "approved":
                        _publish(conn, creator, clip, immediate=True)
            else:
                n = _schedule_creator(conn, creator, created)
                _log(f"{n} Clip(s) für {creator.id} eingeplant/veröffentlicht.")

    _log(f"[auto] Fertig. {len(all_clips)} Clip(s) erzeugt.")
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
        if public:
            creator.posting["privacy_level"] = "PUBLIC_TO_EVERYONE"
        _publish(conn, creator, clip, immediate=True)
        count += 1
    return count
