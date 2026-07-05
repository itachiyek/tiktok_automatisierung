"""Produziert stündlich frischen Nachschub für den Poster.

Rotiert durch die Creator (einer pro Lauf) und lässt die Pipeline aus YouTube
neue Clips erzeugen. Die Pipeline legt Caption automatisch als .txt neben jeden
Render (data/renders/) – genau das, was scripts/post_hourly.py zum Posten braucht.

Bewusst getrennt vom Poster: ein langsamer/hängender Download blockiert so nie
den stündlichen Upload. Rotation-Status: data/rotation_state.json.

Manuell:
  python scripts/produce_hourly.py --dry-run            # zeigt nur, was verarbeitet würde
  python scripts/produce_hourly.py --creator rohaze     # gezielt einen Creator
  python scripts/produce_hourly.py --ignore-window      # Zeitfenster ignorieren
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DATA_DIR, load_config, load_env  # noqa: E402
from src import pipeline  # noqa: E402

STATE = DATA_DIR / "rotation_state.json"
START_HOUR = 6    # ab 06:00 produzieren (1h vor Posting-Start), damit Puffer bereitsteht
END_HOUR = 22
DEFAULT_LIMIT = 2  # bis zu 2 neue YouTube-Quellen je Lauf (danach greift Dedup)


def pick_creator(ids: list[str]) -> str:
    st = {}
    if STATE.exists():
        try:
            st = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    idx = int(st.get("next_index", 0)) % len(ids)
    cid = ids[idx]
    st["next_index"] = (idx + 1) % len(ids)
    st["last"] = {"creator": cid, "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    STATE.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")
    return cid


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--creator", help="gezielt dieser Creator (statt Rotation)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="max. neue Quellen je Lauf")
    ap.add_argument("--ignore-window", action="store_true", help="Zeitfenster ignorieren")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts herunterladen")
    args = ap.parse_args(argv)

    load_env()
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")

    if not args.ignore_window and not (START_HOUR <= now.hour <= END_HOUR):
        print(f"[{stamp}] ausserhalb Produktions-Fenster {START_HOUR}-{END_HOUR} Uhr - uebersprungen.")
        return 0

    cfg = load_config()
    ids = [c.id for c in cfg.creators if c.consent]
    if not ids:
        print(f"[{stamp}] keine Creator mit consent gefunden.")
        return 0

    cid = args.creator if args.creator else pick_creator(ids)
    print(f"[{stamp}] Produktion fuer '{cid}' (limit {args.limit}, dry_run={args.dry_run}) ...")
    try:
        clips = pipeline.run(
            creator_id=cid,
            include_vods=True,      # Twitch-VODs = zuverlässige Quelle (kein YouTube-Bot-Block)
            include_clips=False,    # Community-Clips meist <61s -> zu kurz
            include_youtube=False,  # YouTube-Download aktuell von SABR/PO-Token blockiert
            limit=args.limit,
            dry_run=args.dry_run,
            auto_upload=False,
        )
        print(f"[{stamp}] fertig: {len(clips)} neue(r) Clip(s) fuer {cid}.")
    except Exception as exc:  # noqa
        print(f"[{stamp}] Produktion FEHLER ({cid}): {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
