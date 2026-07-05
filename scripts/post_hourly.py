"""Postet EIN noch nicht gepostetes Video über Zernio – für den stündlichen Cron.

Gedacht für den Windows Task Scheduler (jede Stunde 07–22 Uhr). Pro Lauf:
  1) Fenster prüfen (nur START_HOUR..END_HOUR Uhr posten)
  2) nächstes ungepostetes *.mp4 aus data/renders/ wählen (Plan-Reihenfolge)
  3) über Zernio öffentlich posten
  4) in data/posted_log.json vermerken (damit es nie doppelt kommt)

Manuell testen:
  python scripts/post_hourly.py --dry-run          # zeigt nur den nächsten Clip
  python scripts/post_hourly.py --ignore-window    # jetzt sofort einen posten
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DATA_DIR, RENDER_DIR, load_env  # noqa: E402
from src.upload.zernio import ZernioClient, api_key_from_env  # noqa: E402

LEDGER = DATA_DIR / "posted_log.json"
START_HOUR = 7   # frühestens 07:00 posten
END_HOUR = 22    # spätestens 22:00 posten
NUM_RE = re.compile(r"^(\d+)_")


def clip_number(p: Path) -> int:
    m = NUM_RE.match(p.name)
    return int(m.group(1)) if m else 10**9


def load_ledger() -> dict:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"posted": []}


def save_ledger(d: dict) -> None:
    LEDGER.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def next_unposted(posted_names: set[str]) -> Path | None:
    cand = [
        p for p in RENDER_DIR.glob("*.mp4")
        if p.name not in posted_names and not p.name.endswith("_reframe.mp4")  # Zwischendatei
    ]
    cand.sort(key=lambda p: (clip_number(p), p.name))
    return cand[0] if cand else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="nichts posten, nur nächsten Clip zeigen")
    ap.add_argument("--ignore-window", action="store_true", help="Zeitfenster 07–22 ignorieren")
    ap.add_argument("--privacy", default="PUBLIC_TO_EVERYONE",
                    choices=["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"])
    args = ap.parse_args(argv)

    load_env()
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")

    if not args.ignore_window and not (START_HOUR <= now.hour <= END_HOUR):
        print(f"[{stamp}] ausserhalb Fenster {START_HOUR}-{END_HOUR} Uhr - uebersprungen.")
        return 0

    led = load_ledger()
    posted = {e.get("file") for e in led.get("posted", [])}
    mp4 = next_unposted(posted)
    if not mp4:
        print(f"[{stamp}] keine ungeposteten Clips mehr in {RENDER_DIR}. Neue Clips produzieren.")
        return 0

    txt = mp4.with_suffix(".txt")
    caption = txt.read_text(encoding="utf-8").strip() if txt.exists() else mp4.stem
    print(f"[{stamp}] naechster Clip: {mp4.name}  ({len(posted)} bereits gepostet)")

    if args.dry_run:
        print(f"  (dry-run) Caption: {caption.splitlines()[0][:70]}")
        return 0

    try:
        client = ZernioClient(api_key_from_env())
        acct = client.tiktok_account()
        res = client.post_video(str(mp4), caption, acct["_id"], schedule_iso=None, privacy=args.privacy)
        post = res.get("post", res)
        pid = post.get("_id") or "?"
        status = post.get("status") or "eingereicht"
    except Exception as exc:  # noqa
        print(f"  ✗ FEHLER bei {mp4.name}: {exc}")
        return 1

    led.setdefault("posted", []).append(
        {"file": mp4.name, "at": stamp, "post_id": pid, "status": status,
         "account": acct.get("displayName"), "privacy": args.privacy}
    )
    save_ledger(led)
    print(f"  ✓ gepostet: {mp4.name} -> {acct.get('displayName')} (post {pid}, {status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
