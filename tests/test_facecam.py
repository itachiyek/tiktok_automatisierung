"""Tests fürs Split-Layout (Gesicht groß oben, Video unten) – ohne OpenCV/ffmpeg."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.edit import editor, facecam
from src.edit.facecam import OUT_H, OUT_W, Box
from src.models import Segment

HD = (1920, 1080)


def test_panel_heights_16_9_fits_source_without_bars():
    top, bottom = facecam.panel_heights(*HD)
    assert top + bottom == OUT_H
    # Unteres Panel = exakt die Höhe des Originalbilds in voller Breite (1080/16*9).
    assert abs(bottom - OUT_W * 1080 / 1920) <= 1
    assert top > bottom  # das Gesicht bekommt den größeren Teil


def test_panel_heights_clamped_for_boxy_source():
    top, bottom = facecam.panel_heights(1440, 1080)  # 4:3
    assert top + bottom == OUT_H
    assert bottom <= OUT_H * facecam.BOTTOM_MAX + 1
    assert top >= OUT_H / 2


def test_face_crop_matches_panel_aspect_and_stays_inside():
    top, _ = facecam.panel_heights(*HD)
    face = Box(200, 830, 150, 210)          # Facecam unten links
    crop = facecam.face_crop(*HD, face, top)
    assert 0 <= crop.x and 0 <= crop.y
    assert crop.x + crop.w <= HD[0] and crop.y + crop.h <= HD[1]
    assert abs(crop.w / crop.h - OUT_W / top) < 0.02   # kein Verzerren beim Skalieren
    assert crop.w % 2 == 0 and crop.h % 2 == 0


def test_face_crop_enlarges_face_a_lot():
    """Kernversprechen: das Gesicht wird im Ergebnis deutlich größer als vorher."""
    top, _ = facecam.panel_heights(*HD)
    face = Box(200, 830, 130, 190)
    crop = facecam.face_crop(*HD, face, top)
    zoom = top / crop.h
    face_px_split = face.h * zoom
    # altes Layout: ganzes Bild auf 1080 Breite -> Gesicht schrumpft mit
    face_px_old = face.h * (OUT_W / HD[0])
    assert face_px_split > 3 * face_px_old
    assert face_px_split > 400


def test_face_crop_caps_zoom_for_tiny_faces():
    top, _ = facecam.panel_heights(*HD)
    tiny = Box(900, 500, 30, 40)
    crop = facecam.face_crop(*HD, tiny, top, max_zoom=3.0)
    assert top / crop.h <= 3.0 + 0.05     # sonst wird das Bild Matsch


def test_face_crop_higher_fill_zooms_in():
    top, _ = facecam.panel_heights(*HD)
    face = Box(800, 400, 150, 210)
    near = facecam.face_crop(*HD, face, top, face_fill=0.55, max_zoom=6.0)
    far = facecam.face_crop(*HD, face, top, face_fill=0.30, max_zoom=6.0)
    assert near.h < far.h


def test_face_crop_leaves_headroom_for_the_title():
    """Gesichtsmitte sitzt unterhalb der Panel-Mitte -> oben ist Platz für den Titel."""
    top, _ = facecam.panel_heights(*HD)
    face = Box(880, 400, 160, 220)         # mittig, weit weg von den Rändern
    crop = facecam.face_crop(*HD, face, top)
    assert (face.cy - crop.y) / crop.h > 0.5


def test_face_crop_never_leaves_the_frame_at_the_edge():
    top, _ = facecam.panel_heights(*HD)
    for face in (Box(0, 0, 120, 160), Box(1800, 920, 120, 160)):
        crop = facecam.face_crop(*HD, face, top)
        assert crop.x >= 0 and crop.y >= 0
        assert crop.x + crop.w <= HD[0] and crop.y + crop.h <= HD[1]


def test_face_crop_handles_small_sources():
    """Kleine Quelle (alter Twitch-Clip): Ausschnitt darf nie größer als das Bild sein."""
    small = (640, 360)
    top, _ = facecam.panel_heights(*small)
    crop = facecam.face_crop(*small, Box(60, 240, 50, 70), top)
    assert crop.w <= small[0] and crop.h <= small[1]
    assert crop.x + crop.w <= small[0] and crop.y + crop.h <= small[1]


def test_face_crop_stays_valid_for_every_size_and_position():
    """Breiter Durchlauf: ein Ausschnitt außerhalb des Bildes lässt ffmpeg abbrechen."""
    for src_w, src_h in ((1920, 1080), (1280, 720), (854, 480), (640, 360), (1440, 1080)):
        top, _ = facecam.panel_heights(src_w, src_h)
        for fx in (0, 0.25, 0.5, 0.75, 1.0):
            for fy in (0, 0.25, 0.5, 0.75, 1.0):
                for fh in (24, 90, 300, 900):
                    fw = int(fh * 0.75)
                    face = Box(int((src_w - fw) * fx), int((src_h - fh) * fy), fw, fh)
                    c = facecam.face_crop(src_w, src_h, face, top)
                    assert c.w >= 2 and c.h >= 2, (src_w, src_h, face, c)
                    assert c.x >= 0 and c.y >= 0, (src_w, src_h, face, c)
                    assert c.x + c.w <= src_w and c.y + c.h <= src_h, (src_w, src_h, face, c)
                    assert c.w % 2 == 0 and c.h % 2 == 0


def test_pick_face_ignores_single_outlier():
    stable = [Box(200, 800, 120, 160), Box(206, 804, 122, 158), Box(198, 796, 118, 162)]
    hits = stable + [Box(1500, 100, 130, 170)]     # Fehltreffer in einem Frame
    face = facecam.pick_face(hits, 1280)
    assert face is not None and abs(face.cx - 262) < 25


def test_pick_face_needs_more_than_one_frame():
    assert facecam.pick_face([Box(400, 400, 100, 120)], 1280) is None
    assert facecam.pick_face([], 1280) is None


def test_pick_face_prefers_the_bigger_stable_face():
    small = [Box(100, 100, 60, 70)] * 3             # Plakat im Hintergrund
    big = [Box(900, 600, 180, 230)] * 3             # der Streamer
    face = facecam.pick_face(small + big, 1280)
    assert face is not None and face.w == 180


def test_build_filter_is_a_valid_two_panel_graph():
    layout = facecam.plan(*HD, Box(200, 830, 150, 210))
    graph = facecam.build_filter(layout)
    assert graph.count(";") == 3 and "vstack=inputs=2" in graph
    assert f"crop={layout.crop.w}:{layout.crop.h}:{layout.crop.x}:{layout.crop.y}" in graph
    assert f"scale={OUT_W}:{layout.top_h}" in graph      # oben: Gesicht
    assert f"crop={OUT_W}:{layout.bottom_h}" in graph    # unten: ganzes Bild
    assert layout.top_h + layout.bottom_h == OUT_H


def test_build_reframe_uses_split_when_a_face_is_found(monkeypatch):
    layout = facecam.plan(*HD, Box(200, 830, 150, 210))
    monkeypatch.setattr(facecam, "plan_for_clip", lambda *a, **k: layout)
    graph, is_complex, title_y = editor.build_reframe("x.mp4", Segment(0, 61), editor.FACE_SPLIT, {})
    assert is_complex and "vstack" in graph
    assert title_y == editor.TITLE_Y_SPLIT     # Titel oben, damit er das Gesicht freilässt


def test_build_reframe_falls_back_without_a_face(monkeypatch):
    """Ohne Gesicht (oder ohne OpenCV) darf der Clip nicht scheitern."""
    monkeypatch.setattr(facecam, "plan_for_clip", lambda *a, **k: None)
    graph, is_complex, title_y = editor.build_reframe("x.mp4", Segment(0, 61), editor.FACE_SPLIT, {})
    assert graph == editor.BLUR_PAD and is_complex and title_y == editor.TITLE_Y


def test_build_reframe_keeps_the_old_modes():
    assert editor.build_reframe("x.mp4", Segment(0, 61), "crop", {}) == (editor.CROP, False, editor.TITLE_Y)
    assert editor.build_reframe("x.mp4", Segment(0, 61), "blur_pad", {}) == (editor.BLUR_PAD, True, editor.TITLE_Y)


def test_split_is_the_default_mode():
    assert editor.FACE_SPLIT == "face_split"
    assert editor.cut_and_reframe.__defaults__[0] == editor.FACE_SPLIT
