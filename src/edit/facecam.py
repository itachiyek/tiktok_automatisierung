"""Gesicht des Streamers finden und das 9:16-Split-Layout dafür berechnen.

Layout (1080x1920):
  oben   = stark herangezoomter Ausschnitt um das Gesicht (Facecam/Webcam)
  unten  = das Originalvideo in voller Breite (Gameplay/Content)

Erkennung: YuNet (kleines ONNX-Netz, liegt in models/) über OpenCV. Fehlt das
Modell, greifen die Haar-Cascades aus dem opencv-Wheel – die sind schwächer,
aber immer dabei (nur bis opencv 4.x). cv2 wird bewusst erst *in* den Funktionen
importiert: Die Layout-Mathematik unten läuft (und wird getestet) ohne OpenCV,
und fehlt das Paket ganz, greift der Aufrufer sauber auf das alte Vollbild-
Layout zurück.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

OUT_W = 1080
OUT_H = 1920

# --- Defaults (via defaults.clip in config/creators.yaml überschreibbar) ---
FACE_FILL = 0.44          # Gesichtshöhe im Verhältnis zur Höhe des oberen Panels
FACE_MAX_ZOOM = 3.2       # max. Vergrößerung ggü. der Quelle (Schärfe-Limit)
FACE_CENTER_Y = 0.54      # Gesichtsmitte im oberen Panel (>0.5 = Platz für den Titel)
DETECT_FRAMES = 9         # Stichproben über das Segment
DETECT_WIDTH = 1280       # Analyse-Auflösung (kleine Facecams brauchen Pixel)
MIN_FACE_RATIO = 0.028    # kleinste akzeptierte Gesichtsbreite (Anteil der Bildbreite)
MIN_HITS = 2              # so viele Frames müssen dasselbe Gesicht zeigen
CLUSTER_TOL = 0.10        # Cluster-Toleranz für die Gesichtsmitte (Anteil der Breite)
YUNET_SCORE = 0.6         # Konfidenz-Schwelle von YuNet (Rest filtert das Clustering)

MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"

# Unteres Panel: Anteil an der Gesamthöhe (Grenzen, s. panel_heights()).
BOTTOM_MIN = 0.26
BOTTOM_MAX = 0.46
# Quellen, die schon (fast) hochkant sind, taugen nicht für ein Split-Layout.
MIN_SOURCE_ASPECT = 1.2


def _log(msg: str) -> None:
    print(f"[facecam] {msg}", flush=True)


@dataclass(frozen=True)
class Box:
    """Rechteck in Pixeln (Ursprung oben links)."""

    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> int:
        return self.w * self.h


@dataclass(frozen=True)
class SplitLayout:
    """Fertig gerechnetes Split-Layout für einen Clip."""

    crop: Box       # Gesichts-Ausschnitt in Quell-Pixeln
    top_h: int      # Höhe des oberen Panels (Gesicht)
    bottom_h: int   # Höhe des unteren Panels (Originalvideo)


# --- Layout-Mathematik (rein, ohne OpenCV/ffmpeg) ------------------------
def _even(value: float) -> int:
    """Kantenlänge auf gerade Pixel runden – x264/yuv420p mag keine ungeraden."""
    return max(2, int(round(value / 2)) * 2)


def _even_down(value: float) -> int:
    """Wie _even(), aber immer abrunden – für Offsets und Ober-Grenzen.

    Aufrunden würde den Ausschnitt aus dem Bild schieben (ffmpeg bricht dann ab).
    """
    return max(0, int(value) // 2 * 2)


def panel_heights(src_w: int, src_h: int) -> tuple[int, int]:
    """(oben, unten) in Pixeln.

    Das untere Panel bekommt genau die Höhe, die das Originalbild in voller
    Breite braucht – so bleibt es unbeschnitten und ohne schwarze Balken.
    Der ganze Rest gehört dem Gesicht.
    """
    natural = OUT_W * src_h / max(src_w, 1)
    bottom = _even(min(max(natural, OUT_H * BOTTOM_MIN), OUT_H * BOTTOM_MAX))
    return OUT_H - bottom, bottom


def face_crop(
    src_w: int,
    src_h: int,
    face: Box,
    top_h: int,
    *,
    face_fill: float = FACE_FILL,
    max_zoom: float = FACE_MAX_ZOOM,
    center_y: float = FACE_CENTER_Y,
) -> Box:
    """Ausschnitt um das Gesicht, im Seitenverhältnis des oberen Panels.

    Die Ausschnitthöhe folgt aus der Wunschgröße des Gesichts (`face_fill`),
    wird aber durch `max_zoom` gedeckelt, damit das Bild nicht matschig wird.
    """
    aspect = OUT_W / max(top_h, 1)
    crop_h = face.h / max(face_fill, 0.05)
    crop_h = max(crop_h, top_h / max(max_zoom, 1.0))
    crop_w = crop_h * aspect

    # In die Quelle einpassen (Seitenverhältnis bleibt erhalten).
    fit = min(1.0, src_w / max(crop_w, 1), src_h / max(crop_h, 1))
    crop_w, crop_h = crop_w * fit, crop_h * fit

    # Waagerecht auf das Gesicht zentrieren, senkrecht etwas tiefer setzen –
    # oben bleibt so Luft für die Titel-Karte.
    x = face.cx - crop_w / 2
    y = face.cy - crop_h * center_y

    w = min(_even(crop_w), max(_even_down(src_w), 2))
    h = min(_even(crop_h), max(_even_down(src_h), 2))
    x = _even_down(min(max(x, 0), max(src_w - w, 0)))
    y = _even_down(min(max(y, 0), max(src_h - h, 0)))
    return Box(x, y, w, h)


def build_filter(layout: SplitLayout) -> str:
    """ffmpeg-filter_complex: Gesicht oben, Originalvideo unten, 1080x1920."""
    c = layout.crop
    return (
        "[0:v]split=2[face][full];"
        f"[face]crop={c.w}:{c.h}:{c.x}:{c.y},"
        f"scale={OUT_W}:{layout.top_h}:flags=lanczos,"
        "unsharp=5:5:0.6:5:5:0.0[top];"
        f"[full]scale={OUT_W}:{layout.bottom_h}:"
        "force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OUT_W}:{layout.bottom_h}[bot];"
        "[top][bot]vstack=inputs=2,setsar=1"
    )


def plan(src_w: int, src_h: int, face: Box, cfg: Optional[dict] = None) -> SplitLayout:
    """Gesichts-Box + Quellgröße -> fertiges Split-Layout."""
    cfg = cfg or {}
    top_h, bottom_h = panel_heights(src_w, src_h)
    crop = face_crop(
        src_w, src_h, face, top_h,
        face_fill=float(cfg.get("face_fill", FACE_FILL)),
        max_zoom=float(cfg.get("face_max_zoom", FACE_MAX_ZOOM)),
        center_y=float(cfg.get("face_center_y", FACE_CENTER_Y)),
    )
    return SplitLayout(crop=crop, top_h=top_h, bottom_h=bottom_h)


# --- Quellinfo -----------------------------------------------------------
def probe_size(path: str) -> tuple[int, int]:
    """(Breite, Höhe) des ersten Videostreams; (0, 0) wenn unbekannt."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-select_streams", "v:0", "-show_streams", path],
            capture_output=True, text=True, check=True,
        ).stdout
        st = (json.loads(out).get("streams") or [{}])[0]
        return int(st.get("width", 0) or 0), int(st.get("height", 0) or 0)
    except Exception:
        return 0, 0


# --- Erkennung -----------------------------------------------------------
def _sample_frames(src: str, start: float, end: float, n: int, width: int, dst: Path) -> list[Path]:
    """n Stichproben-Frames gleichmäßig über das Segment als JPEG."""
    dur = max(end - start, 0.5)
    step = max(dur / max(n, 1), 0.04)
    cmd = [
        "ffmpeg", "-y", "-ss", str(max(start, 0)), "-t", str(dur), "-i", src,
        "-vf", f"fps=1/{step:.3f},scale={width}:-2:flags=bilinear",
        "-frames:v", str(n), "-q:v", "4", "-loglevel", "error",
        str(dst / "f_%03d.jpg"),
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return sorted(dst.glob("f_*.jpg"))


class _YuNet:
    """YuNet-Detektor (ONNX). Erkennt auch kleine Facecams und Halbprofile."""

    kind = "yunet"

    def __init__(self, min_px: int, score: float = YUNET_SCORE):
        import cv2  # lazy

        self._cv2 = cv2
        self._min_px = min_px
        self._det = cv2.FaceDetectorYN_create(str(MODEL_PATH), "", (320, 320), score, 0.3, 5000)
        self._size: tuple[int, int] = (0, 0)

    def __call__(self, img) -> list[Box]:
        h, w = img.shape[:2]
        if (w, h) != self._size:
            self._det.setInputSize((w, h))
            self._size = (w, h)
        _, faces = self._det.detect(img)
        out = []
        for f in faces if faces is not None else []:
            x, y, bw, bh = (int(round(v)) for v in f[:4])
            if bw >= self._min_px and bh >= self._min_px:
                out.append(Box(x, y, bw, bh))
        return out


class _Haar:
    """Rückfall ohne ONNX-Modell: Haar-Cascades aus dem opencv-Wheel."""

    kind = "haar"

    def __init__(self, min_px: int):
        import cv2  # lazy

        self._cv2 = cv2
        base = cv2.data.haarcascades
        self._front = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
        prof = cv2.CascadeClassifier(base + "haarcascade_profileface.xml")
        self._profile = None if prof.empty() else prof
        self._min = (min_px, min_px)
        if self._front.empty():
            raise RuntimeError("Haar-Cascades fehlen im OpenCV-Paket (opencv 5 liefert sie nicht mehr)")

    def __call__(self, img) -> list[Box]:
        cv2 = self._cv2
        gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        found = self._front.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=self._min)
        boxes = [Box(int(x), int(y), int(w), int(h)) for x, y, w, h in found]
        if boxes or self._profile is None:
            return boxes
        for x, y, w, h in self._profile.detectMultiScale(gray, 1.1, 6, minSize=self._min):
            boxes.append(Box(int(x), int(y), int(w), int(h)))
        if boxes:
            return boxes
        img_w = gray.shape[1]
        for x, y, w, h in self._profile.detectMultiScale(cv2.flip(gray, 1), 1.1, 6, minSize=self._min):
            boxes.append(Box(int(img_w - x - w), int(y), int(w), int(h)))
        return boxes


def _make_detector(min_px: int):
    """Bester verfügbarer Detektor – oder None, wenn keiner läuft."""
    if MODEL_PATH.exists():
        try:
            return _YuNet(min_px)
        except Exception as exc:
            _log(f"YuNet nicht nutzbar ({exc}) – versuche Haar-Cascades.")
    else:
        _log(f"Modell fehlt ({MODEL_PATH.name}) – versuche Haar-Cascades.")
    try:
        return _Haar(min_px)
    except Exception as exc:
        _log(f"Kein Detektor verfügbar: {exc}")
        return None


def pick_face(boxes: list[Box], img_w: int, min_hits: int = MIN_HITS) -> Optional[Box]:
    """Aus allen Einzel-Treffern das eine stabile Gesicht bestimmen.

    Haar-Cascades liefern auch Fehltreffer. Deshalb werden Treffer nach Position
    geclustert: Nur was über mehrere Frames an derselben Stelle auftaucht, zählt.
    Unter den stabilen Clustern gewinnt der größte – der Streamer, nicht das
    Gesicht auf dem Poster im Hintergrund.
    """
    tol = img_w * CLUSTER_TOL
    clusters: list[list[Box]] = []
    for b in boxes:
        for cl in clusters:
            ref = cl[0]
            if abs(b.cx - ref.cx) <= tol and abs(b.cy - ref.cy) <= tol:
                cl.append(b)
                break
        else:
            clusters.append([b])
    if not clusters:
        return None
    best = max(len(cl) for cl in clusters)
    if best < min_hits:
        return None
    stable = [cl for cl in clusters if len(cl) >= max(min_hits, round(best * 0.5))]
    winner = max(stable, key=lambda cl: _median_box(cl).area)
    return _median_box(winner)


def _median_box(boxes: list[Box]) -> Box:
    def med(vals: list[float]) -> int:
        s = sorted(vals)
        return int(s[len(s) // 2])

    return Box(
        med([b.x for b in boxes]), med([b.y for b in boxes]),
        med([b.w for b in boxes]), med([b.h for b in boxes]),
    )


def _to_head_box(face: Box, src_w: int, src_h: int) -> Box:
    """Enge Gesichts-Box -> Kopf-Box (Haare/Kinn dazu, Mitte leicht nach oben)."""
    w = face.w * 1.18
    h = face.h * 1.32
    cx, cy = face.cx, face.cy - face.h * 0.10
    x = min(max(cx - w / 2, 0), max(src_w - w, 0))
    y = min(max(cy - h / 2, 0), max(src_h - h, 0))
    return Box(int(x), int(y), int(min(w, src_w)), int(min(h, src_h)))


def detect_face(
    src: str,
    start: float,
    end: float,
    src_w: int,
    src_h: int,
    cfg: Optional[dict] = None,
) -> Optional[Box]:
    """Stabilste Gesichts-/Kopf-Box des Segments in Quell-Pixeln (None = keine)."""
    cfg = cfg or {}
    frames = int(cfg.get("face_detect_frames", DETECT_FRAMES))
    width = int(cfg.get("face_detect_width", DETECT_WIDTH))
    try:
        import cv2  # lazy
    except Exception as exc:
        _log(f"OpenCV nicht verfügbar ({exc}) – kein Gesichts-Zuschnitt.")
        return None

    try:
        min_px = max(20, int(width * float(cfg.get("min_face_ratio", MIN_FACE_RATIO))))
        detector = _make_detector(min_px)
        if detector is None:
            return None

        with tempfile.TemporaryDirectory(prefix="facecam_") as tmp:
            paths = _sample_frames(src, start, end, frames, width, Path(tmp))
            if not paths:
                _log("Keine Stichproben-Frames – kein Gesichts-Zuschnitt.")
                return None
            hits: list[Box] = []
            img_w = width
            for p in paths:
                img = cv2.imread(str(p))
                if img is None:
                    continue
                img_w = img.shape[1]
                hits.extend(detector(img))

        face = pick_face(hits, img_w, int(cfg.get("face_min_hits", MIN_HITS)))
        if face is None:
            _log(f"Kein stabiles Gesicht in {len(paths)} Frames "
                 f"({len(hits)} Roh-Treffer, {detector.kind}).")
            return None

        # Analyse lief verkleinert -> zurück in Quell-Koordinaten rechnen.
        s = src_w / max(img_w, 1)
        scaled = Box(int(face.x * s), int(face.y * s), int(face.w * s), int(face.h * s))
        head = _to_head_box(scaled, src_w, src_h)
        _log(f"Gesicht @ {head.x},{head.y} {head.w}x{head.h} "
             f"({len(hits)} Treffer, {detector.kind})")
        return head
    except Exception as exc:
        _log(f"Erkennung fehlgeschlagen: {exc}")
        return None


def plan_for_clip(src: str, start: float, end: float, cfg: Optional[dict] = None) -> Optional[SplitLayout]:
    """Kompletter Weg Quelle -> Layout. None = Split nicht möglich (Fallback)."""
    cfg = cfg or {}
    src_w, src_h = probe_size(src)
    if src_w <= 0 or src_h <= 0:
        _log("Quellgröße unbekannt – kein Gesichts-Zuschnitt.")
        return None
    if src_w / src_h < MIN_SOURCE_ASPECT:
        _log(f"Quelle schon hochkant ({src_w}x{src_h}) – kein Split nötig.")
        return None
    face = detect_face(src, start, end, src_w, src_h, cfg)
    if face is None:
        return None
    return plan(src_w, src_h, face, cfg)
