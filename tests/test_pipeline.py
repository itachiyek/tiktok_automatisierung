"""Tests der reinen Logik (ohne Netzwerk/ffmpeg/Keys)."""
import os
import sys

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
