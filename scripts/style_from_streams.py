"""Learn a live host's *technique* from long stream recordings, without copying him.

    python scripts/style_from_streams.py --urls urls.txt            # all stages
    python scripts/style_from_streams.py --stage download|transcribe|analyze|demos

Stages (each resumable, outputs under training/streamer_style/):
  download   audio only (yt-dlp, m4a)                     -> audio/<id>.m4a
  transcribe faster-whisper on the GPU, with timestamps  -> transcripts/<id>.jsonl  (start, end, text)
  analyze    cadence and interaction statistics           -> style_profile.json, style_report.md
  demos      ORIGINAL demonstrations in Theo's voice,     -> demos.jsonl  (same schema as the streamer pack)
             written by Claude from technique excerpts; no verbatim phrases, trading-education context

What the stream is used for: how often he asks the chat something, how fast he talks, how he greets,
how he calls back to viewers, how he keeps energy up in quiet stretches. What it is NOT used for:
his voice, his catchphrases, his name, his trades. Theo stays Theo.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import re
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "training" / "streamer_style"
AUDIO, TRANS = OUT / "audio", OUT / "transcripts"
LOG = OUT / "pipeline.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("style")


def _log_file(msg: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


# ------------------------------------------------------------------ download
def download(urls: list[str]) -> list[Path]:
    AUDIO.mkdir(parents=True, exist_ok=True)
    out = []
    for u in urls:
        vid = re.search(r"v=([\w-]+)", u)
        vid = vid.group(1) if vid else u.rsplit("/", 1)[-1]
        target = AUDIO / f"{vid}.m4a"
        if target.exists() and target.stat().st_size > 1_000_000:
            out.append(target)
            continue
        log.info("downloading audio %s", vid)
        _log_file(f"download {vid}")
        cmd = [sys.executable, "-m", "yt_dlp", "-f", "bestaudio/best", "-x", "--audio-format", "m4a", "--audio-quality", "5",
               "--no-playlist", "--continue", "--socket-timeout", "20", "--retries", "15", "--fragment-retries", "15",
               "--concurrent-fragments", "4", "--no-progress", "-o", str(AUDIO / "%(id)s.%(ext)s"), f"https://www.youtube.com/watch?v={vid}"]
        ok = False
        for attempt in range(1, 6):                      # a stalled connection is killed and resumed from the .part file
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=45 * 60)
            except subprocess.TimeoutExpired:
                log.warning("download %s stalled (attempt %d); resuming", vid, attempt)
                _log_file(f"download {vid} stalled, attempt {attempt}")
                continue
            if r.returncode == 0 and target.exists():
                ok = True
                break
            log.warning("download %s failed (attempt %d): %s", vid, attempt, r.stderr[-300:])
            time.sleep(30)
        if not ok:
            log.error("download failed %s after retries", vid)
            _log_file(f"download {vid} FAILED")
            continue
        _log_file(f"download {vid} done ({target.stat().st_size // 1_000_000} MB)")
        out.append(target)
    return out


# ------------------------------------------------------------------ transcribe
def _decode_16k(f: Path):
    """Mono float32 PCM at 16 kHz via ffmpeg (what Whisper expects), independent of the PyAV version."""
    import subprocess

    import numpy as np

    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def _cuda_dlls() -> None:
    """CTranslate2 needs cuBLAS 12 / cuDNN 9 DLLs; torch ships them inside the venv, so put those folders on the DLL path."""
    import os

    site = Path(sys.executable).resolve().parents[1] / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
        d = site / sub / "bin"
        if d.exists():
            os.add_dll_directory(str(d))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


def transcribe(files: list[Path], model_name: str = "large-v3-turbo") -> None:
    _cuda_dlls()
    from faster_whisper import WhisperModel

    TRANS.mkdir(parents=True, exist_ok=True)
    from faster_whisper import BatchedInferencePipeline

    try:
        model = WhisperModel(model_name, device="cuda", compute_type="float16")
        log.info("whisper %s on cuda", model_name)
        batch = 16
    except Exception as exc:  # noqa: BLE001
        log.warning("cuda whisper failed (%s); using cpu int8 'small' (slow)", exc)
        model = WhisperModel("small", device="cpu", compute_type="int8")
        batch = 4
    pipeline = BatchedInferencePipeline(model=model)      # batched decoding: several times faster on long files
    for f in files:
        dest = TRANS / f"{f.stem}.jsonl"
        if dest.exists() and dest.stat().st_size > 10_000:
            continue
        log.info("transcribing %s", f.name)
        _log_file(f"transcribe {f.stem} start")
        t0 = time.time()
        audio = _decode_16k(f)            # ffmpeg decode: PyAV >= 15 dropped the keyword faster-whisper's own decoder uses
        try:
            segments, info = pipeline.transcribe(audio, language="en", vad_filter=True, beam_size=1, batch_size=batch, condition_on_previous_text=False)
        except Exception as exc:  # noqa: BLE001
            if "memory" not in str(exc).lower():
                raise
            log.warning("gpu memory tight (%s); retrying with batch 4", str(exc)[:80])
            segments, info = pipeline.transcribe(audio, language="en", vad_filter=True, beam_size=1, batch_size=4, condition_on_previous_text=False)
        n = 0
        tmp = dest.with_suffix(".jsonl.tmp")          # write aside, rename when complete (safe for a parallel transcriber)
        with tmp.open("w", encoding="utf-8") as o:
            for s in segments:
                o.write(json.dumps({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}) + "\n")
                n += 1
        tmp.replace(dest)
        _log_file(f"transcribe {f.stem} done: {n} segments in {time.time() - t0:.0f}s (audio {info.duration:.0f}s)")
        log.info("done %s: %d segments, %.0fs", f.stem, n, time.time() - t0)


# ------------------------------------------------------------------ analyze
QUESTION = re.compile(r"\?\s*$|^(what|who|where|when|why|how|which|do you|did you|are you|is it|can you|anyone|anybody)\b", re.I)
GREET = re.compile(r"\b(what's up|whats up|welcome|hey|yo|good (morning|evening|night)|hello|thanks for (the|coming)|appreciate)\b", re.I)
LAUGH = re.compile(r"\b(haha|lol|lmao)\b|\[laughter\]", re.I)
CHAT = re.compile(r"\b(chat|guys|everyone|everybody|you guys|y'all)\b", re.I)
HYPE = re.compile(r"\b(let's go|lets go|come on|oh my|look at (this|that)|boom|wow|here we go|no way|there it is)\b|!", re.I)
NAME = re.compile(r"\b(?:hey|thanks|thank you|welcome|what's up|whats up|yo|shout ?out to)\s+([A-Z][a-z]{2,15})\b")


def analyze() -> dict:
    files = sorted(TRANS.glob("*.jsonl"))
    if not files:
        raise SystemExit("no transcripts yet")
    per_stream = []
    all_text = []
    for f in files:
        segs = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not segs:
            continue
        dur = max(s["end"] for s in segs) / 60.0
        words = sum(len(s["text"].split()) for s in segs)
        speech_min = sum(s["end"] - s["start"] for s in segs) / 60.0
        q = sum(1 for s in segs if QUESTION.search(s["text"]))
        greet = sum(1 for s in segs if GREET.search(s["text"]))
        laugh = sum(1 for s in segs if LAUGH.search(s["text"]))
        chat = sum(1 for s in segs if CHAT.search(s["text"]))
        hype = sum(1 for s in segs if HYPE.search(s["text"]))
        names = Counter(m for s in segs for m in NAME.findall(s["text"]))
        gaps = [segs[i + 1]["start"] - segs[i]["end"] for i in range(len(segs) - 1)]
        long_gaps = sum(1 for g in gaps if g > 8)
        sent_len = [len(s["text"].split()) for s in segs]
        # how often he asks something vs just talks: seconds between questions
        q_times = [s["start"] for s in segs if QUESTION.search(s["text"])]
        q_gap = statistics.median([b - a for a, b in zip(q_times, q_times[1:])]) if len(q_times) > 2 else None
        per_stream.append({
            "stream": f.stem, "minutes": round(dur, 1), "talk_share": round(speech_min / max(dur, 1), 2),
            "wpm_while_talking": round(words / max(speech_min, 1), 1), "questions_per_10min": round(q / max(dur, 1) * 10, 2),
            "median_s_between_questions": round(q_gap, 1) if q_gap else None, "greetings_per_10min": round(greet / max(dur, 1) * 10, 2),
            "chat_addresses_per_10min": round(chat / max(dur, 1) * 10, 2), "hype_lines_per_10min": round(hype / max(dur, 1) * 10, 2),
            "laughs_per_10min": round(laugh / max(dur, 1) * 10, 2), "silences_over_8s_per_hour": round(long_gaps / max(dur / 60, 1e-6), 1),
            "median_sentence_words": statistics.median(sent_len) if sent_len else 0, "distinct_viewer_names": len(names),
        })
        all_text.extend(s["text"] for s in segs)
    def med(k):
        v = [p[k] for p in per_stream if p.get(k) is not None]
        return round(statistics.median(v), 2) if v else None
    profile = {
        "source": "ten ~5 h live sessions of one cheerful day-trading host (technique reference only)",
        "streams": per_stream,
        "summary": {k: med(k) for k in ("talk_share", "wpm_while_talking", "questions_per_10min", "median_s_between_questions", "greetings_per_10min",
                                       "chat_addresses_per_10min", "hype_lines_per_10min", "laughs_per_10min", "silences_over_8s_per_hour", "median_sentence_words")},
    }
    # technique vocabulary: frequent short moves (counted as categories; Theo paraphrases, never copies)
    moves = Counter()
    for t in all_text:
        tl = t.lower()
        if GREET.search(tl): moves["greeting / welcome by name"] += 1
        if QUESTION.search(tl): moves["asks the chat a question"] += 1
        if CHAT.search(tl): moves["addresses the chat directly"] += 1
        if HYPE.search(tl): moves["energy spike / reaction"] += 1
        if LAUGH.search(tl): moves["laughs / self-deprecating"] += 1
        if re.search(r"\b(earlier|like i said|remember when|as i mentioned|we talked about)\b", tl): moves["callback to earlier"] += 1
        if re.search(r"\b(if you('re| are) (new|just)|for (anyone|those) (new|just))\b", tl): moves["orients newcomers"] += 1
        if re.search(r"\b(stop|risk|invalid|wrong|lose|loss)\b", tl): moves["talks risk / being wrong"] += 1
    profile["technique_counts"] = dict(moves.most_common())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "style_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    s = profile["summary"]
    report = ["# Host technique profile (reference only)", "", f"Streams analysed: {len(per_stream)}", "",
              "| metric | median |", "|---|---|"] + [f"| {k} | {v} |" for k, v in s.items()] + ["", "## Technique counts (all streams)", ""] + \
             [f"- {k}: {v}" for k, v in profile["technique_counts"].items()] + ["",
              "## What Theo takes from this", "",
              "- Cadence: the host talks most of the time, asks the chat something every few minutes, and greets people by name constantly.",
              "- Energy: short reactions on real events, laughter at himself, never dead air for long.",
              "- Continuity: callbacks to earlier moments and to viewers; orientation for newcomers.",
              "- Theo paraphrases the technique in a trading-education context; no catchphrases, voice or identity are copied."]
    (OUT / "style_report.md").write_text("\n".join(report), encoding="utf-8")
    log.info("profile written: %s", json.dumps(s))
    return profile


# ------------------------------------------------------------------ demos (original, via Claude)
DEMO_SYSTEM = """You write ORIGINAL training demonstrations for "Theo", an AI trading teacher who streams live on TikTok.
You are shown a short excerpt from a different live host's stream, purely as a reference for a TECHNIQUE
(how he greets, asks the chat, reacts, calls back, keeps energy up). Write a new demonstration of the same
technique in Theo's own words, in a trading-education context (charts, levels, risk, no signals/predictions).
Never copy phrases, names, catchphrases or trades from the excerpt. No emojis. Return JSON only."""

DEMO_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "skill": {"type": "string", "enum": ["orientation", "explanation", "chat_selection", "callbacks", "tone", "timing", "grounding", "speech_readiness"]},
        "technique": {"type": "string"},
        "input": {"type": "object", "additionalProperties": False, "properties": {
            "event": {"type": "string", "enum": ["chat", "timer", "session_start", "market_update"]},
            "topic": {"type": "string"}, "facts": {"type": "array", "items": {"type": "string"}},
            "chat": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
                "id": {"type": "string"}, "display_name": {"type": "string"}, "text": {"type": "string"}, "age_seconds": {"type": "integer"}},
                "required": ["id", "display_name", "text", "age_seconds"]}},
            "recent_host_text": {"type": "array", "items": {"type": "string"}}, "memory": {"type": "array", "items": {"type": "string"}},
            "speech_busy": {"type": "boolean"}, "question_pending": {"type": "boolean"}},
            "required": ["event", "topic", "facts", "chat", "recent_host_text", "memory", "speech_busy", "question_pending"]},
        "target": {"type": "object", "additionalProperties": False, "properties": {
            "action": {"type": "string", "enum": ["respond", "commentate", "wait"]}, "reply_to": {"type": ["string", "null"]},
            "speech": {"type": "string"}, "delivery": {"type": "string", "enum": ["warm", "calm", "curious", "amused", "focused", "cheerful", "excited", "considerate", "none"]},
            "follow_up": {"type": ["string", "null"]}}, "required": ["action", "reply_to", "speech", "delivery", "follow_up"]},
    },
    "required": ["skill", "technique", "input", "target"],
}


def _excerpts(n: int, window_s: float = 90.0, rng: random.Random | None = None) -> list[dict]:
    rng = rng or random.Random(11)
    pool = []
    for f in sorted(TRANS.glob("*.jsonl")):
        segs = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        i = 0
        while i < len(segs):
            t0 = segs[i]["start"]
            chunk = []
            while i < len(segs) and segs[i]["start"] - t0 < window_s:
                chunk.append(segs[i]); i += 1
            text = " ".join(c["text"] for c in chunk)
            score = len(QUESTION.findall(text)) * 2 + len(GREET.findall(text)) * 2 + len(CHAT.findall(text)) + len(HYPE.findall(text)) + len(NAME.findall(text)) * 2
            if score >= 4 and len(text.split()) > 80:
                pool.append({"stream": f.stem, "start": t0, "text": text[:1800], "score": score})
    pool.sort(key=lambda e: -e["score"])
    top = pool[: max(n * 3, 1)]
    rng.shuffle(top)
    return top[:n]


async def demos(n: int) -> None:
    from app.brain.agent_backend import structured_json
    from app.brain.client import CHAT_MODEL

    dest = OUT / "demos.jsonl"
    have = sum(1 for _ in dest.open(encoding="utf-8")) if dest.exists() else 0
    todo = _excerpts(n)[have:]
    log.info("writing %d original demos (have %d)", len(todo), have)
    with dest.open("a", encoding="utf-8") as o:
        for k, ex in enumerate(todo, have + 1):
            user = (f"EXCERPT (reference for the technique only, {ex['stream']} at {int(ex['start'])}s):\n\"\"\"{ex['text']}\"\"\"\n\n"
                    "Identify the single strongest engagement technique in it and write ONE original demonstration of that technique for Theo "
                    "in the JSON schema. The situation must be a trading-education live stream (gold or Bitcoin chart), with fictional viewer names, "
                    "and the speech must be something Theo would say in his own voice.")
            try:
                obj, usage = await asyncio.to_thread(structured_json, DEMO_SCHEMA, DEMO_SYSTEM, user, CHAT_MODEL, 1500)
            except Exception as exc:  # noqa: BLE001
                log.warning("demo %d failed: %s", k, str(exc)[:160])
                _log_file(f"demo {k} failed: {str(exc)[:120]}")
                if "limit" in str(exc).lower():
                    log.warning("subscription limit; stopping demos for now (re-run later to continue)")
                    break
                continue
            row = {"id": f"st_{k:04d}", "scenario_group": f"stream_{ex['stream']}_{int(ex['start'])}", "split": "train", "provenance": "original_from_technique_reference",
                   "human_reviewed": False, **obj, "reviewer_note": ""}
            o.write(json.dumps(row) + "\n"); o.flush()
            _log_file(f"demo {k} ok ({obj.get('skill')}: {obj.get('technique', '')[:60]})")
            log.info("demo %d: %s / %s", k, obj.get("skill"), obj.get("technique", "")[:60])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", help="file with one YouTube URL per line")
    ap.add_argument("--stage", choices=["all", "download", "transcribe", "analyze", "demos"], default="all")
    ap.add_argument("--demos", type=int, default=150)
    ap.add_argument("--model", default="large-v3-turbo")
    a = ap.parse_args()
    urls = [l.strip() for l in Path(a.urls).read_text(encoding="utf-8").splitlines() if l.strip()] if a.urls else []
    if a.stage in ("all", "download"):
        files = download(urls)
    else:
        files = sorted(AUDIO.glob("*.m4a"))
    if a.stage in ("all", "transcribe"):
        transcribe(files, a.model)
    if a.stage in ("all", "analyze"):
        analyze()
    if a.stage in ("all", "demos"):
        asyncio.run(demos(a.demos))
    _log_file(f"stage {a.stage} finished")


if __name__ == "__main__":
    main()
