"""Cut a recording into one clip per lesson using the segment log the director writes
(data_cache/segments.jsonl: {"kind": "lesson", "topic": ..., "start": ts, "end": ts}).

    .venv\\Scripts\\python -m app.clips.cutter recordings\\20261026_160000.mp4 [--max-seconds 90]

Each clip gets the disclosure burned in at the bottom and lands in clips_out/.
Post them manually with TikTok's "AI-generated content" toggle ON.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

SEGMENTS = Path("data_cache/segments.jsonl")
OUT = Path("clips_out")
DISCLOSURE = "Haddan · Chart Room · educational only · not financial advice"


def load_segments(kind: str = "lesson") -> list[dict]:
    if not SEGMENTS.exists():
        return []
    segs = []
    for line in SEGMENTS.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("kind") == kind and d.get("end"):
            segs.append(d)
    return segs


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def cut(recording: Path, max_seconds: int = 90, min_seconds: int = 25) -> list[Path]:
    meta = json.loads(recording.with_suffix(".json").read_text())
    rec_start = float(meta["started"])
    OUT.mkdir(exist_ok=True)
    made = []
    for seg in load_segments():
        s, e = float(seg["start"]) - rec_start, float(seg["end"]) - rec_start
        if s < 0:
            continue
        dur = min(e - s, max_seconds)
        if dur < min_seconds:
            continue
        out = OUT / f"{recording.stem}_{slug(seg.get('topic', 'lesson'))}.mp4"
        draw = (f"drawtext=text='{DISCLOSURE}':fontcolor=white@0.85:fontsize=30:box=1:boxcolor=black@0.5:boxborderw=12:"
                f"x=(w-text_w)/2:y=h-th-40")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-ss", f"{s:.2f}", "-i", str(recording), "-t", f"{dur:.2f}",
               "-vf", draw, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=False)
        if out.exists():
            made.append(out)
            print("clip ->", out)
    return made


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("recording")
    ap.add_argument("--max-seconds", type=int, default=90)
    a = ap.parse_args()
    cut(Path(a.recording), a.max_seconds)
