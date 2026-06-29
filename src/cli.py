"""CLI-Einstieg:  python -m src.cli <command>

Befehle:
  check                 Konfiguration + API-Keys prüfen (zeigt, was fehlt)
  init-db               Datenbank anlegen
  run                   Pipeline laufen lassen (Ingest -> Clip -> ggf. Upload)
  clips                 Erzeugte Clips auflisten
  approve <id...>       Clips freigeben (pending_review -> approved)
  upload-approved       Alle freigegebenen Clips hochladen
"""
from __future__ import annotations

import argparse
import os
import sys

from . import db, pipeline
from .config import (
    anthropic_api_key,
    load_config,
    tiktok_credentials,
    twitch_credentials,
    youtube_api_key,
)


def _status(label: str, ok: bool, hint: str = "") -> None:
    mark = "✅" if ok else "❌"
    extra = "" if ok else (f"  -> {hint}" if hint else "")
    print(f"  {mark} {label}{extra}")


def cmd_check(args) -> int:
    print("== API-Keys / Umgebung ==")
    tcid, tsec = twitch_credentials()
    _status("Twitch CLIENT_ID/SECRET", bool(tcid and tsec), "TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET in .env")
    _status("YouTube API-Key", bool(youtube_api_key()), "YOUTUBE_API_KEY in .env (optional, nur für YT-Uploads)")
    _status("Anthropic API-Key", bool(anthropic_api_key()), "ANTHROPIC_API_KEY in .env (sonst Template-Texte)")
    kcid, ksec = tiktok_credentials()
    _status("TikTok CLIENT_KEY/SECRET", bool(kcid and ksec), "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET in .env")

    print("\n== Tools ==")
    from shutil import which

    _status("ffmpeg", which("ffmpeg") is not None, "ffmpeg installieren (apt/brew)")
    _status("ffprobe", which("ffprobe") is not None, "Teil von ffmpeg")

    print("\n== Creator-Config ==")
    try:
        cfg = load_config()
    except Exception as exc:
        print(f"  ❌ Config-Fehler: {exc}")
        return 1
    for c in cfg.creators:
        token = c.tiktok_access_token()
        _status(
            f"{c.name} ({c.id})  consent={c.consent}  tiktok_token={'ja' if token else 'nein'}",
            c.consent and bool(token),
            f"Einwilligung + TIKTOK_ACCESS_TOKEN_{c.id.upper()} setzen",
        )
    return 0


def cmd_init_db(args) -> int:
    db.init_db()
    print("Datenbank initialisiert.")
    return 0


def cmd_run(args) -> int:
    pipeline.run(
        creator_id=args.creator,
        dry_run=args.dry_run,
        limit=args.limit,
        include_vods=args.vods,
        include_youtube=args.youtube,
        auto_upload=args.auto_upload,
    )
    return 0


def cmd_clips(args) -> int:
    conn = db.init_db()
    clips = db.list_clips(conn, status=args.status, creator_id=args.creator)
    if not clips:
        print("Keine Clips gefunden.")
        return 0
    for c in clips:
        tags = " ".join((c.meta.hashtags if c.meta else [])[:4])
        print(f"#{c.id:>4}  {c.status:<14} {c.creator_id:<10} {c.segment.duration:>5.0f}s  {c.path}")
        if c.meta and c.meta.caption:
            print(f"        ↳ {c.meta.caption[:80]}  {tags}")
    return 0


def cmd_approve(args) -> int:
    conn = db.init_db()
    for cid in args.ids:
        db.update_status(conn, int(cid), "approved")
        print(f"Clip #{cid} -> approved")
    return 0


def cmd_upload_approved(args) -> int:
    n = pipeline.upload_approved(creator_id=args.creator, public=args.public)
    print(f"{n} Clip(s) hochgeladen.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tiktok-pipeline", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Konfiguration & Keys prüfen").set_defaults(func=cmd_check)
    sub.add_parser("init-db", help="Datenbank anlegen").set_defaults(func=cmd_init_db)

    r = sub.add_parser("run", help="Pipeline ausführen")
    r.add_argument("--creator", help="nur dieser Creator (id)")
    r.add_argument("--limit", type=int, default=3, help="max. Quellen pro Creator")
    r.add_argument("--dry-run", action="store_true", help="nur Ingest zeigen, nichts schneiden/hochladen")
    r.add_argument("--vods", action="store_true", help="auch volle Twitch-VODs analysieren")
    r.add_argument("--youtube", action="store_true", help="auch neue YouTube-Uploads")
    r.add_argument("--auto-upload", action="store_true", help="freigegebene Clips direkt hochladen")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("clips", help="Clips auflisten")
    c.add_argument("--status", help="filtern: new|pending_review|approved|uploaded|failed")
    c.add_argument("--creator", help="filtern nach Creator-id")
    c.set_defaults(func=cmd_clips)

    a = sub.add_parser("approve", help="Clips freigeben")
    a.add_argument("ids", nargs="+", help="Clip-IDs")
    a.set_defaults(func=cmd_approve)

    u = sub.add_parser("upload-approved", help="freigegebene Clips hochladen")
    u.add_argument("--creator", help="nur dieser Creator")
    u.add_argument("--public", action="store_true", help="öffentlich posten (nur nach TikTok-Audit!)")
    u.set_defaults(func=cmd_upload_approved)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
