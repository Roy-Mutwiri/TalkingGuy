"""Live progress board: everything that is being built or downloaded, in one JSON for the /progress page.

Reads only files and logs (cheap, safe to poll every 2 s): the streamer study pipeline, model downloads in
the Hugging Face cache, the teacher's own status file and the GPU.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "training" / "streamer_style"
HF = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
EXPECTED_MB = {"models--mobiuslabsgmbh--faster-whisper-large-v3-turbo": 1600}


def _dir_mb(p: Path) -> float:
    if not p.exists():
        return 0.0
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total / 1e6


def _tail(p: Path, n: int = 8) -> list[str]:
    if not p.exists():
        return []
    try:
        return p.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
    except OSError:
        return []


def study() -> dict:
    urls = [l.strip() for l in (STUDY / "urls.txt").read_text(encoding="utf-8").splitlines() if l.strip()] if (STUDY / "urls.txt").exists() else []
    ids = [re.search(r"v=([\w-]+)", u).group(1) if re.search(r"v=([\w-]+)", u) else u for u in urls]
    rows = []
    for vid in ids:
        m4a = STUDY / "audio" / f"{vid}.m4a"
        part = next(iter((STUDY / "audio").glob(f"{vid}.*.part")), None) if (STUDY / "audio").exists() else None
        tr = STUDY / "transcripts" / f"{vid}.jsonl"
        tmp = STUDY / "transcripts" / f"{vid}.jsonl.tmp"
        rows.append({
            "id": vid,
            "download": "done" if m4a.exists() else ("downloading" if part else "queued"),
            "download_mb": round((m4a.stat().st_size if m4a.exists() else (part.stat().st_size if part else 0)) / 1e6),
            "transcript": "done" if tr.exists() else ("running" if tmp.exists() else "queued"),
            "segments": sum(1 for _ in tr.open(encoding="utf-8")) if tr.exists() else 0,
        })
    demos = STUDY / "demos.jsonl"
    return {
        "streams": rows,
        "downloaded": sum(1 for r in rows if r["download"] == "done"), "transcribed": sum(1 for r in rows if r["transcript"] == "done"), "total": len(rows),
        "profile": (STUDY / "style_profile.json").exists(), "report": (STUDY / "style_report.md").exists(),
        "demos": sum(1 for _ in demos.open(encoding="utf-8")) if demos.exists() else 0,
        "log": _tail(STUDY / "pipeline.log", 6),
    }


def downloads() -> list[dict]:
    out = []
    for name, exp in EXPECTED_MB.items():
        got = _dir_mb(HF / name)
        out.append({"name": name.replace("models--", "").replace("--", "/"), "mb": round(got), "expected_mb": exp, "pct": min(100, round(got / exp * 100))})
    return out


def gpu() -> dict:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=4)
        used, total, util, temp = [int(x.strip()) for x in r.stdout.strip().split(",")]
        return {"used_mb": used, "total_mb": total, "util": util, "temp": temp}
    except Exception:  # noqa: BLE001
        return {}


def teacher() -> dict:
    st = ROOT / "data_cache" / "status.json"
    try:
        d = json.loads(st.read_text(encoding="utf-8")) if st.exists() else {}
    except json.JSONDecodeError:
        d = {}
    log = ROOT / "logs" / "stream.log"
    lines = _tail(log, 600)
    d["last_lesson"] = next((l[34:150] for l in reversed(lines) if "director: lesson: " in l), "")
    d["last_say"] = next((l[40:200] for l in reversed(lines) if "director: say: " in l), "")
    d["utterances_recent"] = sum(1 for l in lines if "director: say: " in l)
    d["nonverbal_recent"] = sum(1 for l in lines if "nonverbal:" in l)
    d["scrubs_recent"] = sum(1 for l in lines if "director: deai: " in l)
    return d


def collect() -> dict:
    return {"time": time.strftime("%H:%M:%S"), "study": study(), "downloads": downloads(), "gpu": gpu(), "teacher": teacher()}
