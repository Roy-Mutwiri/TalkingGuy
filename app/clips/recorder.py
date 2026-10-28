"""Record the stage window + the teacher's voice with ffmpeg, so lessons can be cut into
short vertical clips for the feed (the fallback if LIVE access is restricted).

    .venv\\Scripts\\python -m app.clips.recorder            # records until Ctrl+C -> recordings/<timestamp>.mp4
    .venv\\Scripts\\python -m app.clips.recorder --minutes 60

Video: gdigrab of the window titled "Chart Room stage" (started by start_stream.bat).
Audio: dshow "CABLE Output (VB-Audio Virtual Cable)" (what LIVE Studio hears).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RECORDINGS = Path("recordings")
WINDOW_TITLE = "Chart Room stage"
AUDIO_DEVICE = "CABLE Output (VB-Audio Virtual Cable)"


def record(minutes: float | None, window_title: str = WINDOW_TITLE, audio_device: str = AUDIO_DEVICE) -> Path:
    RECORDINGS.mkdir(exist_ok=True)
    started = datetime.now(timezone.utc)
    out = RECORDINGS / f"{started.strftime('%Y%m%d_%H%M%S')}.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-f", "gdigrab", "-framerate", "30", "-i", f"title={window_title}",
        "-f", "dshow", "-i", f"audio={audio_device}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
    ]
    if minutes:
        cmd += ["-t", str(int(minutes * 60))]
    cmd.append(str(out))
    meta = {"started": started.timestamp(), "file": str(out)}
    (out.with_suffix(".json")).write_text(json.dumps(meta))
    print("recording ->", out, "(Ctrl+C to stop)")
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        pass
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=None)
    ap.add_argument("--window", default=WINDOW_TITLE)
    ap.add_argument("--audio", default=AUDIO_DEVICE)
    a = ap.parse_args()
    record(a.minutes, a.window, a.audio)
