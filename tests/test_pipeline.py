"""Tests der reinen Logik (ohne Netzwerk/ffmpeg/Keys)."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db
from src.highlight.audio_energy import pick_segments
from src.ingest.twitch import _parse_twitch_duration
from src.ingest.youtube import _parse_iso8601_duration
from src.metadata import generator
from src.models import Clip, ClipMeta, Segment, SourceItem, TWITCH_CLIP
from src.review import quality_gate


def test_segment_helpers():
    s = Segment(10.0, 75.0)
    assert s.duration == 65.0
    assert SourceItem("x", TWITCH_CLIP, "id1", "t", "u").is_pre_clipped


def test_pick_segments_picks_loudest_non_overlapping():
    energies = [0.1] * 300
    energies[50] = 0.9   # Peak 1 (~50s)
    energies[200] = 0.8  # Peak 2 (~200s)
    segs = pick_segments(energies, window_sec=1.0, target_len=65, max_clips=2, min_gap_sec=45)
    assert len(segs) == 2
    centers = sorted((s.start + s.end) / 2 for s in segs)
    assert abs(centers[0] - 50) < 35 and abs(centers[1] - 200) < 35
    # keine Überlappung
    a, b = sorted(segs, key=lambda s: s.start)
    assert a.end <= b.start + 1


def test_pick_segments_empty():
    assert pick_segments([], 1.0) == []


def test_duration_parsers():
    assert _parse_twitch_duration("1h2m3s") == 3723
    assert _parse_twitch_duration("45s") == 45
    assert _parse_iso8601_duration("PT1H2M3S") == 3723
    assert _parse_iso8601_duration("PT30S") == 30


def test_metadata_fallback_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    src = SourceItem("trymacs", TWITCH_CLIP, "abc", "Krasse Aktion", "http://x")
    meta = generator.generate({"niche": ["gaming"], "tone": "hyped"}, "Trymacs", src)
    assert meta.caption
    assert any("#fyp" == h for h in meta.hashtags)
    assert len(meta.hashtags) <= 8
    cap = meta.tiktok_caption()
    assert "#" in cap


def test_clipmeta_caption_formatting():
    m = ClipMeta("t", "Hook!", ["fyp", "#gaming"])
    cap = m.tiktok_caption()
    assert "#fyp" in cap and "#gaming" in cap


def test_quality_gate_duplicate_and_duration(tmp_path):
    conn = db.init_db(db.connect(":memory:"))
    # zu kurz
    short = Clip("trymacs", "twitch_clip:1", Segment(0, 10))
    f = tmp_path / "x.mp4"
    f.write_bytes(b"0" * 100_000)
    short.path = str(f)
    ok, reason = quality_gate.check(conn, short, {"min_duration_sec": 61, "max_duration_sec": 90})
    assert not ok and "kurz" in reason

    good = Clip("trymacs", "twitch_clip:2", Segment(0, 65), path=str(f), meta=ClipMeta("t", "c", []))
    ok, _ = quality_gate.check(conn, good, {"min_duration_sec": 61, "max_duration_sec": 90})
    assert ok
    db.save_clip(conn, good)
    # jetzt Duplikat
    dup = Clip("trymacs", "twitch_clip:2", Segment(0, 65), path=str(f))
    ok, reason = quality_gate.check(conn, dup, {"min_duration_sec": 61, "max_duration_sec": 90})
    assert not ok and "Duplikat" in reason


def test_build_auth_url():
    from src.upload.tiktok_auth import build_auth_url

    url = build_auth_url("CK123", "http://localhost:8080/callback", ["user.info.basic", "video.publish"], "st_x")
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/?")
    assert "client_key=CK123" in url
    assert "video.publish" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fcallback" in url
    assert "state=st_x" in url


def test_db_roundtrip():
    conn = db.init_db(db.connect(":memory:"))
    c = Clip("eligella", "twitch_clip:9", Segment(0, 65), path="/x.mp4", meta=ClipMeta("T", "Cap", ["#a"]))
    cid = db.save_clip(conn, c)
    assert cid > 0
    got = db.get_clip(conn, cid)
    assert got and got.creator_id == "eligella" and got.meta.hashtags == ["#a"]
    db.update_status(conn, cid, "approved")
    assert db.list_clips(conn, status="approved")[0].id == cid


# --------------------------------------------------------------------------- #
# Untertitel-Position (Requirement: gesprochene Texte OBEN)
# --------------------------------------------------------------------------- #
def test_subtitle_alignment_defaults_to_top():
    from src.edit import subtitles

    assert subtitles.resolve_alignment("top") == 8
    assert subtitles.resolve_alignment("bottom") == 2
    assert subtitles.resolve_alignment("middle") == 5
    assert subtitles.resolve_alignment("") == 8   # Standard = oben
    assert subtitles.resolve_alignment(None) == 8


def test_write_ass_burns_text_at_top(tmp_path):
    from src.edit import subtitles

    out = tmp_path / "sub.ass"
    subtitles.write_ass([(0.0, 1.0, "Hallo Welt")], str(out), position="top")
    text = Path(out).read_text(encoding="utf-8")
    # Style-Zeile: Alignment=8 (oben-mitte), MarginV=230
    assert ",8,60,60,230,1" in text
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Pop,,0,0,0,,Hallo Welt" in text


def test_write_ass_bottom_still_supported(tmp_path):
    from src.edit import subtitles

    out = tmp_path / "sub_b.ass"
    subtitles.write_ass([(0.0, 1.0, "x")], str(out), position="bottom")
    assert ",2,60,60,300,1" in Path(out).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Clip-Länge 1–2 Minuten
# --------------------------------------------------------------------------- #
def test_target_length_is_clamped():
    from src.highlight.selector import _target_length

    cfg = {"min_duration_sec": 60, "max_duration_sec": 120, "target_duration_sec": 90}
    assert _target_length(cfg) == 90
    assert _target_length({**cfg, "target_duration_sec": 9999}) == 120
    assert _target_length({**cfg, "target_duration_sec": 5}) == 60


def test_pre_clipped_capped_at_two_minutes():
    from src.highlight.selector import select_segments

    cfg = {"min_duration_sec": 60, "max_duration_sec": 120, "target_duration_sec": 90}
    long_src = SourceItem("trymacs", TWITCH_CLIP, "a", "t", "u", duration_sec=200.0)
    segs = select_segments(long_src, "/nonexistent", cfg)
    assert len(segs) == 1 and segs[0].duration == 120.0  # auf 2 min gedeckelt

    ok_src = SourceItem("trymacs", TWITCH_CLIP, "b", "t", "u", duration_sec=75.0)
    segs2 = select_segments(ok_src, "/nonexistent", cfg)
    assert segs2[0].duration == 75.0  # passt bereits ins Fenster


def test_quality_gate_rejects_over_two_minutes(tmp_path):
    conn = db.init_db(db.connect(":memory:"))
    f = tmp_path / "c.mp4"
    f.write_bytes(b"0" * 100_000)
    cfg = {"min_duration_sec": 60, "max_duration_sec": 120}
    # 90 s -> ok
    ok, _ = quality_gate.check(conn, Clip("t", "k:1", Segment(0, 90), path=str(f)), cfg)
    assert ok
    # 150 s -> zu lang (Grenze 120 + 3 s Toleranz)
    bad, reason = quality_gate.check(conn, Clip("t", "k:2", Segment(0, 150), path=str(f)), cfg)
    assert not bad and "lang" in reason


def test_decide_status_auto_approve():
    assert quality_gate.decide_status({"require_human_review": True}) == "pending_review"
    assert quality_gate.decide_status({"require_human_review": True}, auto_approve=True) == "approved"


# --------------------------------------------------------------------------- #
# Zernio-Integration (reine Payload-/Auflösungslogik, ohne Netz)
# --------------------------------------------------------------------------- #
def test_zernio_match_account():
    from src.upload.zernio import match_account

    accts = [
        {"_id": "a1", "username": "@trymacs.clips"},
        {"_id": "a2", "username": "eligella.clips"},
    ]
    assert match_account(accts, "@trymacs.clips") == "a1"
    assert match_account(accts, "eligella.clips") == "a2"
    assert match_account(accts, "unbekannt") is None          # mehrdeutig, kein Treffer
    assert match_account([{"_id": "solo", "username": "x"}], "y") == "solo"  # einziges Konto
    assert match_account([], "x") is None


def test_zernio_post_body_scheduled():
    from src.upload.zernio import build_tiktok_post_body

    when = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
    b = build_tiktok_post_body("acc1", "Hook!", "https://media/x.mp4", when=when)
    assert b["platforms"] == [{"platform": "tiktok", "accountId": "acc1"}]
    assert b["mediaItems"][0] == {"type": "video", "url": "https://media/x.mp4"}
    assert b["content"] == "Hook!"
    assert b["scheduledFor"] == "2026-07-04T12:00:00+00:00"
    assert "publishNow" not in b and "isDraft" not in b
    ts = b["tiktokSettings"]
    assert ts["privacyLevel"] == "PUBLIC_TO_EVERYONE"
    assert ts["allowDuet"] is True and ts["allowStitch"] is True


def test_zernio_post_body_publish_draft_and_default():
    from src.upload.zernio import build_tiktok_post_body

    pub = build_tiktok_post_body("a", "c", "u", publish_now=True)
    assert pub["publishNow"] is True and "scheduledFor" not in pub

    draft = build_tiktok_post_body("a", "c", "u", is_draft=True)
    assert draft["isDraft"] is True and "scheduledFor" not in draft

    default = build_tiktok_post_body("a", "c", "u")  # ohne Modus -> sofort (sichere Vorgabe)
    assert default["publishNow"] is True


def test_schedule_times_spacing():
    from src.pipeline import schedule_times

    base = datetime(2026, 7, 4, 10, 0, 0, tzinfo=timezone.utc)
    times = schedule_times(3, first_delay_min=20, spacing_min=180, base=base)
    assert [t.isoformat() for t in times] == [
        "2026-07-04T10:20:00+00:00",
        "2026-07-04T13:20:00+00:00",
        "2026-07-04T16:20:00+00:00",
    ]
    assert schedule_times(0, 20, 180, base) == []


def test_creator_uploader_selection(monkeypatch):
    from src.config import Creator

    monkeypatch.delenv("ZERNIO_API_KEY", raising=False)
    c = Creator({"id": "x"}, {"posting": {}})
    assert c.uploader() == "tiktok"                    # kein Key -> Legacy
    monkeypatch.setenv("ZERNIO_API_KEY", "sk_test")
    assert c.uploader() == "zernio"                    # Key vorhanden -> Zernio
    c2 = Creator({"id": "y"}, {"posting": {"uploader": "tiktok"}})
    assert c2.uploader() == "tiktok"                   # explizit gesetzt gewinnt


def test_creator_zernio_account_id(monkeypatch):
    from src.config import Creator

    monkeypatch.delenv("ZERNIO_ACCOUNT_ID_Z", raising=False)
    c = Creator({"id": "z", "zernio_account_id": "acc_123"}, {})
    assert c.zernio_account_id() == "acc_123"
    c2 = Creator({"id": "z"}, {})
    monkeypatch.setenv("ZERNIO_ACCOUNT_ID_Z", "acc_env")
    assert c2.zernio_account_id() == "acc_env"
