"""ffmpeg-Orchestrierung: Segment schneiden -> 9:16 -> Untertitel + Creator-Credit."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from ..models import Segment
from . import subtitles

# 9:16-Filter, blur_pad: Original mittig auf unscharfem, formatfüllendem Hintergrund.
BLUR_PAD = (
    "[0:v]split=2[bg][fg];"
    "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
    "crop=1080:1920,boxblur=24[bg];"
    "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
    "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
)
# crop: mittiger 9:16-Ausschnitt (Inhalt am Rand geht verloren).
CROP = "crop=ih*9/16:ih,scale=1080:1920,setsar=1"


def ffprobe_duration(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, check=True,
        ).stdout
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return 0.0


def _run(cmd: list, cwd: Optional[str] = None) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg fehlgeschlagen: {proc.stderr[-800:]}")


def cut_and_reframe(src: str, seg: Segment, out: str, mode: str = "blur_pad") -> str:
    vf = BLUR_PAD if mode == "blur_pad" else CROP
    cmd = ["ffmpeg", "-y", "-ss", str(seg.start), "-to", str(seg.end), "-i", src]
    if mode == "blur_pad":
        cmd += ["-filter_complex", vf]
    else:
        cmd += ["-vf", vf]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        "-loglevel", "error", out,
    ]
    _run(cmd)
    return out


def burn(src: str, out: str, ass_path: Optional[str], credit: Optional[str]) -> str:
    filters = []
    cwd = None
    if ass_path:
        # ffmpeg im Ordner der .ass ausführen und nur den Dateinamen referenzieren.
        # So entfällt das Windows-Pfad-Problem (Laufwerk-':' bricht den Filtergraph).
        ass_p = Path(ass_path)
        cwd = str(ass_p.parent)
        filters.append(f"ass={_escape(ass_p.name)}")
    if credit:
        txt = credit.replace(":", r"\:").replace("'", "")
        filters.append(
            "drawtext=text='" + txt + "':fontcolor=white:fontsize=40:"
            "x=(w-text_w)/2:y=h-150:box=1:boxcolor=black@0.45:boxborderw=12"
        )
    if not filters:
        # nichts zu brennen -> nur kopieren
        _run(["ffmpeg", "-y", "-i", src, "-c", "copy", "-loglevel", "error", out])
        return out
    cmd = [
        "ffmpeg", "-y", "-i", src, "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy", "-movflags", "+faststart", "-loglevel", "error", out,
    ]
    _run(cmd, cwd=cwd)
    return out


def _escape(name: str) -> str:
    # Filtergraph-Sonderzeichen im (reinen) Dateinamen maskieren.
    return name.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def make_clip(
    source_path: str,
    seg: Segment,
    clip_cfg: dict,
    credit_text: Optional[str],
    work_dir: str,
    basename: str,
    language: str = "de",
    top_title: str = "",
) -> str:
    """Voller Edit-Pfad: Rückgabe = Pfad zur fertigen 9:16-MP4.

    Keine gesprochenen Untertitel mehr – nur ein kurzer Titel (3–5 Wörter) oben.
    """
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    mode = clip_cfg.get("reframe_mode", "blur_pad")

    inter = str(work / f"{basename}_reframe.mp4")
    cut_and_reframe(source_path, seg, inter, mode=mode)

    ass_path = None
    if top_title:
        try:
            dur = ffprobe_duration(inter) or (seg.end - seg.start)
            ass_path = subtitles.write_title_ass(top_title, str(work / f"{basename}.ass"), dur)
        except Exception:
            ass_path = None  # Titel optional – Clip trotzdem erzeugen

    credit = credit_text if clip_cfg.get("show_creator_credit", False) else None
    final = str(work / f"{basename}.mp4")
    burn(inter, final, ass_path, credit)
    return final
