"""Play a lesson JSON on the stage with synthetic candles, with or without the real voice.

  1. start the hub:   .venv\\Scripts\\python -m app.main
  2. open http://127.0.0.1:8000/stage in Chrome (1080x1920)
  3. run:             .venv\\Scripts\\python scripts\\dry_run_lesson.py tests\\fixtures\\sample_lesson.json [--voice]

The script acts as a tiny director: it connects to /ws/control, resolves each `load`
into candles (synthetic random walk around price 100 so the fixture's hlines make sense),
sends captions and mouth levels, and waits for replay_done before moving on.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import websockets  # noqa: E402

from app.brain.schema import LessonScript, iso_to_unix  # noqa: E402

TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}


def synthetic_candles(start: int, end: int, step: int, seed: int = 7) -> list[dict]:
    rnd = random.Random(seed)
    out: list[dict] = []
    price, t = 104.0, start
    while t < end:
        drift = -0.25 if len(out) < 40 else 0.35
        o = price
        c = max(95.0, o + drift + rnd.gauss(0, 0.9))
        h = max(o, c) + abs(rnd.gauss(0, 0.5))
        lo = min(o, c) - abs(rnd.gauss(0, 0.5))
        out.append({"time": t, "open": round(o, 2), "high": round(h, 2), "low": round(lo, 2),
                    "close": round(c, 2), "volume": int(500 + abs(rnd.gauss(0, 300)))})
        price, t = c, t + step
    return out


def words_duration_ms(text: str) -> int:
    return int(len(text.split()) / 2.6 * 1000)  # ~2.6 words per second


async def fake_speak(send, text: str) -> None:
    """Caption + fake mouth movement when no TTS is available."""
    dur = words_duration_ms(text)
    await send({"type": "caption", "text": text, "duration_ms": dur})
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    while (loop.time() - t0) * 1000 < dur:
        await send({"type": "mouth", "level": abs(math.sin(loop.time() * 9)) * 0.9})
        await asyncio.sleep(0.05)
    await send({"type": "mouth", "level": 0})


async def real_speak(send, speaker, text: str) -> None:
    async for ev in speaker.speak(text):
        if ev["event"] == "sentence":
            await send({"type": "caption", "text": ev["text"], "duration_ms": ev["duration_ms"]})
        elif ev["event"] == "level":
            await send({"type": "mouth", "level": ev["level"]})
    await send({"type": "mouth", "level": 0})


async def run(path: str, host: str, voice: bool) -> None:
    script = LessonScript.model_validate_json(Path(path).read_text(encoding="utf-8"))
    speaker = None
    if voice:
        from app.voice.kokoro_tts import Speaker  # lazy import: needs torch + kokoro
        speaker = Speaker()

    async with websockets.connect(f"ws://{host}/ws/control", max_size=2**24) as ws:
        replay_done = asyncio.Event()

        async def reader():
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "replay_done":
                    replay_done.set()

        reader_task = asyncio.create_task(reader())

        async def send(obj):
            await ws.send(json.dumps(obj))

        async def say(text: str):
            if speaker:
                await real_speak(send, speaker, text)
            else:
                await fake_speak(send, text)

        header = {"type": "lesson", "title": script.topic, "module": script.module, "summary": script.summary, "total": len(script.beats)}
        await send({"type": "mode", "value": "lesson"})
        await send({**header, "step": 0})
        await asyncio.sleep(0.5)

        for i, beat in enumerate(script.beats, 1):
            await send({**header, "step": i})
            await send({"type": "beat"})
            wait_replay = False
            for act in beat.chart:
                d = act.model_dump()
                if d["action"] == "load":
                    step = TF_SECONDS[d["tf"]]
                    s, e = iso_to_unix(d["start"]), iso_to_unix(d["end"])
                    d["candles"] = synthetic_candles(s, e, step)
                    replay_done.clear()
                    wait_replay = bool(d["replay"])
                for k in ("time", "start", "end", "t1", "t2"):
                    if k in d and isinstance(d[k], str):
                        d[k] = iso_to_unix(d[k])
                await send({"type": "chart", **d})
            await say(beat.say)
            if wait_replay:
                try:
                    await asyncio.wait_for(replay_done.wait(), timeout=30)
                except asyncio.TimeoutError:
                    print("warning: replay_done not received")
            await asyncio.sleep(beat.pause_ms / 1000)

        if script.quiz:
            await send({"type": "question", "user": "Quick quiz", "text": script.quiz.question})
            await say(script.quiz.question)
            await asyncio.sleep(2)
            await say(script.quiz.answer)
            await asyncio.sleep(1)
            await send({"type": "question", "clear": True})
        await send({"type": "caption", "text": ""})
        reader_task.cancel()
        print("lesson finished")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("lesson", nargs="?", default="tests/fixtures/sample_lesson.json")
    ap.add_argument("--host", default="127.0.0.1:8000")
    ap.add_argument("--voice", action="store_true", help="speak with Kokoro instead of fake mouth movement")
    a = ap.parse_args()
    asyncio.run(run(a.lesson, a.host, a.voice))
