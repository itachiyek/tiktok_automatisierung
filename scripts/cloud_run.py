"""Cloud-Runner für GitHub Actions: produziert Twitch-Clips und plant sie in Zernio ein.

Läuft komplett in der Cloud (PC aus). Ablauf pro Lauf:
  1) Zernio-Warteschlange prüfen (wie viele Posts sind noch in der Zukunft geplant?)
  2) Fehlt Vorrat (< TARGET), aus Twitch-VODs neue Clips produzieren (Creator-Rotation)
  3) Neue Clips in Zernio einplanen – stündlich 07–22 Uhr (Europe/Berlin), hinter den
     letzten bereits geplanten Slot
  4) State (data/clips.db Dedup + data/posted_log.json Ledger) wird vom Workflow ins Repo
     zurück-committet, damit nichts doppelt kommt.

Der Zernio-Cloud postet die geplanten Clips dann selbst zur Uhrzeit – unabhängig vom Runner.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DATA_DIR, RENDER_DIR, load_config, load_env  # noqa: E402
from src import pipeline  # noqa: E402
from src.upload.zernio import ZernioClient, api_key_from_env  # noqa: E402

LEDGER = DATA_DIR / "posted_log.json"
STATE = DATA_DIR / "rotation_state.json"
BERLIN = ZoneInfo("Europe/Berlin")
UTC = timezone.utc
START_HOUR, END_HOUR = 7, 22  # stündliche Slots (Ortszeit)


def _load(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _rotate_creator(ids: list[str]) -> str:
    st = _load(STATE, {})
    idx = int(st.get("next_index", 0)) % len(ids)
    st["next_index"] = (idx + 1) % len(ids)
    _save(STATE, st)
    return ids[idx]


def unscheduled_clips(ledger: dict) -> list[Path]:
    done = {e.get("file") for e in ledger.get("posted", [])}
    out = [
        p for p in RENDER_DIR.glob("*.mp4")
        if not p.name.endswith("_reframe.mp4") and p.name not in done
    ]
    out.sort(key=lambda p: p.name)
    return out


def future_count(ledger: dict) -> int:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return sum(1 for e in ledger.get("posted", []) if (e.get("scheduled_utc") or "") > now)


def last_scheduled(ledger: dict) -> datetime:
    times = [e.get("scheduled_utc") for e in ledger.get("posted", []) if e.get("scheduled_utc")]
    now = datetime.now(UTC)
    if not times:
        return now
    latest = max(times)
    try:
        dt = datetime.strptime(latest, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except Exception:
        return now
    return max(now, dt)


def next_slots(count: int, not_before: datetime) -> list[str]:
    """`count` stündliche Slots 07–22 Uhr (Berlin) nach `not_before`, als UTC-ISO."""
    start_berlin = not_before.astimezone(BERLIN)
    out: list[str] = []
    day = start_berlin.date()
    while len(out) < count:
        for h in range(START_HOUR, END_HOUR + 1):
            cand = datetime(day.year, day.month, day.day, h, 0, tzinfo=BERLIN)
            if cand <= start_berlin:
                continue
            out.append(cand.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
            if len(out) >= count:
                break
        day = day + timedelta(days=1)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=int, default=24, help="Ziel-Vorrat an geplanten Posts")
    ap.add_argument("--max-new", type=int, default=8, help="max. neue Clips pro Lauf (CI-Zeit begrenzen)")
    ap.add_argument("--per-source", type=int, default=2, help="Quellen (VODs) je Creator-Versuch")
    ap.add_argument("--privacy", default="PUBLIC_TO_EVERYONE")
    ap.add_argument("--no-schedule", action="store_true", help="nur produzieren, nicht in Zernio einplanen (Test)")
    args = ap.parse_args(argv)

    load_env()
    for d in (DATA_DIR, RENDER_DIR):
        d.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    ids = [c.id for c in cfg.creators if c.consent]
    ledger = _load(LEDGER, {"posted": []})

    have = future_count(ledger)
    need = max(0, min(args.target - have, args.max_new))
    print(f"[cloud] geplanter Vorrat: {have} | Ziel: {args.target} | erzeuge bis zu: {need}")

    # 1) Produzieren, bis genug ungeplante Clips da sind (oder Rotation erschöpft)
    attempts = 0
    while len(unscheduled_clips(ledger)) < need and attempts < len(ids) * 2:
        cid = _rotate_creator(ids)
        print(f"[cloud] Produktion: {cid} (Versuch {attempts + 1})")
        try:
            pipeline.run(
                creator_id=cid, include_vods=True, include_clips=False,
                include_youtube=False, limit=args.per_source, auto_upload=False,
            )
        except Exception as exc:  # noqa
            print(f"[cloud] Produktion {cid} Fehler: {exc}")
        attempts += 1

    clips = unscheduled_clips(ledger)[:need]
    print(f"[cloud] {len(clips)} neue Clip(s) bereit zum Einplanen.")

    if args.no_schedule or not clips:
        for p in clips:
            print("   +", p.name)
        return 0

    # 2) In Zernio einplanen (hinter den letzten geplanten Slot)
    client = ZernioClient(api_key_from_env())
    acct = client.tiktok_account()
    aid = acct["_id"]
    slots = next_slots(len(clips), last_scheduled(ledger))
    ok = 0
    for mp4, slot in zip(clips, slots):
        txt = mp4.with_suffix(".txt")
        caption = txt.read_text(encoding="utf-8").strip() if txt.exists() else mp4.stem
        try:
            res = client.post_video(str(mp4), caption, aid, schedule_iso=slot, privacy=args.privacy)
            pid = (res.get("post") or {}).get("_id") or res.get("_id") or "?"
            ledger["posted"].append({
                "file": mp4.name, "scheduled_utc": slot, "post_id": pid,
                "account": acct.get("displayName"), "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            _save(LEDGER, ledger)  # nach jedem Post speichern (robust bei Abbruch)
            print(f"  ✓ {mp4.name} -> geplant {slot} (post {pid})")
            ok += 1
        except Exception as exc:  # noqa
            print(f"  ✗ {mp4.name}: {exc}")
    print(f"[cloud] fertig: {ok}/{len(clips)} eingeplant. Neuer Vorrat: {future_count(ledger)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
