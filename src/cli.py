"""CLI-Einstieg:  python -m src.cli <command>

Befehle:
  check                 Konfiguration + API-Keys prüfen (zeigt, was fehlt)
  init-db               Datenbank anlegen
  run                   Pipeline laufen lassen (Ingest -> Clip -> ggf. Upload)
  auto                  Vollautomatik für Crons: Cut + Auto-Freigabe + Zernio-Planung
  post                  Ein einzelnes Video direkt via Zernio posten/planen
  zernio-accounts       In Zernio verbundene Konten auflisten (accountId finden)
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
    load_env,
    tiktok_credentials,
    tiktok_redirect_uri,
    twitch_credentials,
    youtube_api_key,
    zernio_api_key,
    zernio_base_url,
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
    _status("TikTok CLIENT_KEY/SECRET", bool(kcid and ksec),
            "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET in .env (nur für Legacy-Direktupload)")
    _status("Zernio API-Key", bool(zernio_api_key()),
            "ZERNIO_API_KEY in .env (empfohlener Upload-/Planungsweg, kein eigenes TikTok-Audit nötig)")

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
        uploader = c.uploader()
        if uploader == "zernio":
            ready = c.consent and bool(zernio_api_key())
            resolved = c.zernio_account_id() or f"auto({c.tiktok_account or '?'})"
            detail = f"zernio_account={resolved}"
            hint = "Einwilligung + ZERNIO_API_KEY setzen (Konto in Zernio verbinden)"
        else:
            token = c.tiktok_access_token()
            ready = c.consent and bool(token)
            detail = f"tiktok_token={'ja' if token else 'nein'}"
            hint = f"Einwilligung + TIKTOK_ACCESS_TOKEN_{c.id.upper()} setzen"
        _status(
            f"{c.name} ({c.id})  consent={c.consent}  uploader={uploader}  {detail}",
            ready, hint,
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


def cmd_auto(args) -> int:
    pipeline.run_auto(
        creator_id=args.creator,
        limit=args.limit,
        include_vods=not args.no_vods,
        include_youtube=args.youtube,
        dry_run=args.dry_run,
        force_now=args.now,
    )
    return 0


def _parse_when(args):
    """Liefert (when, publish_now) aus --now/--in/--at."""
    from datetime import datetime, timedelta, timezone

    if getattr(args, "at", None):
        raw = args.at.replace("Z", "+00:00")
        return datetime.fromisoformat(raw), False
    if getattr(args, "in_min", None):
        return datetime.now(timezone.utc) + timedelta(minutes=int(args.in_min)), False
    return None, True  # Standard: sofort


def cmd_post(args) -> int:
    """Ein einzelnes Video direkt via Zernio posten/planen (ohne Cut-Pipeline)."""
    from .upload.zernio import ZernioClient, ZernioError

    key = zernio_api_key()
    if not key:
        print("❌ ZERNIO_API_KEY fehlt in der .env.")
        return 1
    if not args.file and not args.url:
        print("❌ Bitte --file <pfad> ODER --url <öffentliche Video-URL> angeben.")
        return 1

    # Creator-Kontext (optional) für Handle/Privacy/Timezone.
    creator = None
    if args.creator:
        try:
            creator = load_config().get(args.creator)
        except Exception:
            creator = None
    username = creator.tiktok_account if creator else None
    account_id = args.account_id or (creator.zernio_account_id() if creator else None)
    privacy = args.privacy or (creator.posting.get("privacy_level") if creator else None) or "PUBLIC_TO_EVERYONE"
    tz = (creator.posting.get("timezone") if creator else None) or "UTC"

    when, publish_now = _parse_when(args)

    # Dry-Run: Request-Body OHNE Netzwerk zeigen (Konto/Media als Platzhalter, falls unbekannt).
    if args.dry_run:
        from .upload.zernio import build_tiktok_post_body
        import json as _json

        body = build_tiktok_post_body(
            account_id or "<ACCOUNT_ID (auto-aufgeloest)>",
            args.caption or "",
            args.url or f"<upload:{args.file}>",
            when=when, publish_now=publish_now, privacy_level=privacy, timezone=tz,
        )
        print("[dry-run] Request-Body an POST /v1/posts:")
        print(_json.dumps(body, indent=2, ensure_ascii=False))
        return 0

    try:
        client = ZernioClient(key, zernio_base_url())
        resolved_account = client.resolve_account_id("tiktok", username=username, account_id=account_id)
        print(f"→ Konto: {resolved_account}")

        # Medien-URL bestimmen (URL direkt nutzen, sonst Datei hochladen).
        if args.url:
            media_url = args.url
        else:
            print(f"→ lade Video hoch: {args.file}")
            media_url = client.upload_video(args.file)
            print(f"→ öffentliche URL: {media_url}")

        pid = client.create_tiktok_post(
            resolved_account, args.caption or "", media_url,
            when=when, publish_now=publish_now, privacy_level=privacy, timezone=tz,
        )
        mode = "sofort veröffentlicht" if publish_now else f"geplant für {when.isoformat()}"
        print(f"✅ TikTok-Post {mode} (privacy={privacy}). Zernio-Post-ID: {pid}")
        return 0
    except ZernioError as exc:
        print(f"❌ {exc}")
        return 1
    except Exception as exc:
        print(f"❌ Post fehlgeschlagen: {exc}")
        return 1


def cmd_zernio_accounts(args) -> int:
    from .upload.zernio import ZernioClient, ZernioError

    key = zernio_api_key()
    if not key:
        print("❌ ZERNIO_API_KEY fehlt in der .env.")
        return 1
    try:
        client = ZernioClient(key, zernio_base_url())
        accounts = client.list_accounts(platform=args.platform)
    except ZernioError as exc:
        print(f"❌ {exc}")
        return 1
    except Exception as exc:
        print(f"❌ Abruf fehlgeschlagen: {exc}")
        return 1
    if not accounts:
        print("Keine verbundenen Konten gefunden. Zuerst unter https://zernio.com verbinden.")
        return 0
    print(f"{len(accounts)} verbundene(s) Konto/Konten:")
    for a in accounts:
        aid = a.get("_id") or a.get("id")
        print(f"  {a.get('platform', '?'):<12} {str(a.get('username', '')):<24} id={aid}")
    print("\nTipp: setze die passende id als 'zernio_account_id' in config/creators.yaml.")
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


def cmd_auth(args) -> int:
    from .upload import tiktok_auth

    ck, cs = tiktok_credentials()
    if not (ck and cs):
        print("❌ TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET fehlen in der .env.")
        return 1
    try:
        tiktok_auth.run_oauth(
            args.creator, ck, cs, tiktok_redirect_uri(), manual=args.manual
        )
    except Exception as exc:
        print(f"❌ OAuth fehlgeschlagen: {exc}")
        return 1
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

    au2 = sub.add_parser("auto", help="Vollautomatik (Cron): Cut + Auto-Freigabe + Zernio-Planung")
    au2.add_argument("--creator", help="nur dieser Creator (id)")
    au2.add_argument("--limit", type=int, default=3, help="max. Quellen pro Creator")
    au2.add_argument("--no-vods", action="store_true", help="Twitch-VODs NICHT analysieren (nur fertige Clips)")
    au2.add_argument("--youtube", action="store_true", help="auch neue YouTube-Uploads")
    au2.add_argument("--now", action="store_true", help="sofort veröffentlichen statt gestaffelt planen")
    au2.add_argument("--dry-run", action="store_true", help="nur zeigen, was verarbeitet würde")
    au2.set_defaults(func=cmd_auto)

    za = sub.add_parser("zernio-accounts", help="in Zernio verbundene Konten auflisten")
    za.add_argument("--platform", default="tiktok", help="Plattform-Filter (Standard: tiktok)")
    za.set_defaults(func=cmd_zernio_accounts)

    po = sub.add_parser("post", help="ein einzelnes Video direkt via Zernio posten/planen")
    po.add_argument("--file", help="lokale Videodatei (wird zu Zernio hochgeladen)")
    po.add_argument("--url", help="öffentliche Video-URL (statt Datei-Upload)")
    po.add_argument("--caption", default="", help="Caption/Beschreibung (mit Hashtags)")
    po.add_argument("--creator", help="Creator-id für Handle/Privacy/Timezone (optional)")
    po.add_argument("--account-id", dest="account_id", help="Zernio-Konto-ID direkt (optional)")
    po.add_argument("--privacy", help="PUBLIC_TO_EVERYONE (Standard) oder SELF_ONLY")
    po.add_argument("--now", action="store_true", help="sofort veröffentlichen (Standard)")
    po.add_argument("--in", dest="in_min", type=int, help="in N Minuten planen")
    po.add_argument("--at", help="Zeitpunkt planen (ISO, z. B. 2026-07-05T18:00:00Z)")
    po.add_argument("--dry-run", action="store_true", help="nur Request-Body zeigen, nichts senden")
    po.set_defaults(func=cmd_post)

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

    au = sub.add_parser("auth", help="TikTok-Konto autorisieren -> Access-Token erzeugen")
    au.add_argument("--creator", required=True, help="Creator-id (z. B. trymacs)")
    au.add_argument("--manual", action="store_true", help="ohne lokalen Server: Redirect-URL einfügen")
    au.set_defaults(func=cmd_auth)
    return p


def main(argv=None) -> int:
    load_env()  # .env fuer alle Befehle laden (Keys aus ENV/.env verfuegbar machen)
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
