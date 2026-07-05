"""Postet die gerenderten Clips aus data/renders/ über die Zernio-API auf TikTok.

Beispiele:
  # Trockenlauf: was würde gepostet?
  python scripts/post_via_zernio.py --dry-run

  # Nur Clip 01 SOFORT posten (Verifikation)
  python scripts/post_via_zernio.py --only 1

  # Clips 2..34 mit 7 Posts/Tag terminieren (ab morgen)
  python scripts/post_via_zernio.py --start 2 --schedule

Jeder Clip NN_*.mp4 wird mit seiner gleichnamigen NN_*.txt (Caption+Hashtags) gepaart.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import RENDER_DIR, load_env  # noqa: E402
from src.upload.zernio import ZernioClient, api_key_from_env  # noqa: E402

# Tages-Slots (Ortszeit): stündlich 07–22 Uhr = 16 Posts/Tag.
SLOTS = [f"{h:02d}:00" for h in range(7, 23)]
NUM_RE = re.compile(r"^(\d+)_")


def clip_number(p: Path) -> int:
    m = NUM_RE.match(p.name)
    return int(m.group(1)) if m else 10**9


def load_clips(renders_dir: Path) -> list[tuple[int, Path, str]]:
    out = []
    for mp4 in sorted(renders_dir.glob("*.mp4"), key=clip_number):
        if mp4.name.endswith("_reframe.mp4"):  # Zwischendatei der Pipeline überspringen
            continue
        txt = mp4.with_suffix(".txt")
        caption = txt.read_text(encoding="utf-8").strip() if txt.exists() else mp4.stem
        out.append((clip_number(mp4), mp4, caption))
    return out


def schedule_times(count: int, start_dt_local: datetime) -> list[datetime]:
    """Erzeugt `count` Ortszeit-Termine über die SLOTS (7/Tag), ab start_dt_local."""
    slots = [tuple(int(x) for x in s.split(":")) for s in SLOTS]
    times: list[datetime] = []
    day = start_dt_local.date()
    while len(times) < count:
        for hh, mm in slots:
            cand = datetime(day.year, day.month, day.day, hh, mm)
            if cand <= start_dt_local:
                continue
            times.append(cand)
            if len(times) >= count:
                break
        day = day + timedelta(days=1)
    return times


def to_utc_iso(local_dt: datetime) -> str:
    return local_dt.astimezone().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--renders-dir", default=str(RENDER_DIR))
    ap.add_argument("--only", type=int, help="nur diese Clip-Nummer posten (sofort, außer --schedule)")
    ap.add_argument("--start", type=int, default=1, help="ab dieser Clip-Nummer (Batch)")
    ap.add_argument("--limit", type=int, help="max. Anzahl Clips im Batch")
    ap.add_argument("--schedule", action="store_true", help="terminiert posten (7/Tag) statt sofort")
    ap.add_argument("--start-in-min", type=int, default=15, help="erster geplanter Post frühestens in N Minuten")
    ap.add_argument("--privacy", default="PUBLIC_TO_EVERYONE",
                    choices=["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"])
    ap.add_argument("--private", action="store_true", help="Kurzform für --privacy SELF_ONLY (nur für dich sichtbar)")
    ap.add_argument("--username", help="TikTok-Username, falls mehrere Konten verbunden")
    ap.add_argument("--dry-run", action="store_true", help="nichts posten, nur anzeigen")
    args = ap.parse_args(argv)

    load_env()
    privacy = "SELF_ONLY" if args.private else args.privacy

    clips = load_clips(Path(args.renders_dir))
    if args.only is not None:
        clips = [c for c in clips if c[0] == args.only]
    else:
        clips = [c for c in clips if c[0] >= args.start]
        if args.limit:
            clips = clips[: args.limit]
    if not clips:
        print("Keine passenden Clips gefunden.")
        return 1

    # Zeitplan berechnen
    sched: list = [None] * len(clips)
    if args.schedule:
        start_local = datetime.now() + timedelta(minutes=args.start_in_min)
        sched = schedule_times(len(clips), start_local)

    print(f"== {len(clips)} Clip(s) | privacy={privacy} | {'GEPLANT' if args.schedule else 'SOFORT'} ==")
    for (num, mp4, caption), when in zip(clips, sched):
        cap1 = caption.splitlines()[0][:60]
        when_s = when.strftime("%a %d.%m. %H:%M") if when else "jetzt"
        print(f"  #{num:>2} {when_s:>16}  {mp4.name}  ↳ {cap1}")

    if args.dry_run:
        print("\n(Trockenlauf – nichts gepostet.)")
        return 0

    key = api_key_from_env()
    client = ZernioClient(key)
    acct = client.tiktok_account(args.username)
    account_id = acct["_id"]
    print(f"\nZiel-Konto: {acct.get('displayName')}  (id {account_id})\n")

    ok = 0
    for (num, mp4, caption), when in zip(clips, sched):
        schedule_iso = to_utc_iso(when) if when else None
        try:
            res = client.post_video(str(mp4), caption, account_id, schedule_iso=schedule_iso, privacy=privacy)
            pid = res.get("post", {}).get("_id") or res.get("_id") or res.get("id") or "?"
            status = res.get("post", {}).get("status") or res.get("status") or "eingereicht"
            tag = when.strftime("%d.%m. %H:%M") if when else "jetzt"
            print(f"  ✓ #{num:>2} {mp4.name}  -> {tag}  (post {pid}, {status})")
            ok += 1
        except Exception as exc:  # noqa
            print(f"  ✗ #{num:>2} {mp4.name}  FEHLER: {exc}")
    print(f"\nFertig: {ok}/{len(clips)} an Zernio übergeben.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
