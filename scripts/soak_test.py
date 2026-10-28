"""Run the whole system offline for N minutes (no voice, no TikTok) and report whether it
kept teaching without crashing. Simulated viewer questions are injected via the console channel.

    .venv\\Scripts\\python scripts\\soak_test.py --minutes 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = [
    "what is a doji candle?", "how do you find support and resistance?", "is bitcoin going to 100k?",
    "should I buy eth now?", "are you a real person?", "what timeframe is best for beginners?",
    "explain risk management please", "what does volume tell you?", "how do I know when a trend ends?",
]


async def inject_questions(port: int, stop: asyncio.Event) -> int:
    import websockets

    n = 0
    while not stop.is_set():
        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws/control") as ws:
                while not stop.is_set():
                    await asyncio.sleep(random.uniform(30, 70))
                    q = random.choice(QUESTIONS)
                    await ws.send(json.dumps({"type": "operator", "cmd": "ask", "user": f"viewer{random.randint(1, 99)}", "text": q}))
                    n += 1
        except Exception:  # noqa: BLE001
            await asyncio.sleep(5)
    return n


async def main(minutes: float, port: int) -> int:
    log_path = ROOT / "logs" / "stream.log"
    log_path.parent.mkdir(exist_ok=True)
    start_size = log_path.stat().st_size if log_path.exists() else 0
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([sys.executable, "-m", "app.run", "--offline", "--no-voice", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stop = asyncio.Event()
    t0 = time.time()
    injector = asyncio.create_task(inject_questions(port, stop))
    try:
        while time.time() - t0 < minutes * 60:
            if proc.poll() is not None:
                print("FAIL: process exited early with", proc.returncode)
                return 1
            await asyncio.sleep(5)
    finally:
        stop.set()
        injector.cancel()
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    text = log_path.read_text(encoding="utf-8", errors="ignore")[start_size:]
    lessons = len(re.findall(r"director: lesson:", text))
    crashes = len(re.findall(r"crashed|Traceback", text))
    answered = len(re.findall(r"operator: ask", text))
    titles = re.findall(r"director: lesson: (.+?) \(", text)
    repeats = len(titles) - len(set(titles))
    print(f"ran {minutes} min: lessons={lessons} questions_injected={answered} crashes={crashes} repeated_titles={repeats}")
    ok = lessons >= max(1, int(minutes / 4)) and crashes == 0 and repeats == 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--port", type=int, default=8011)
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.minutes, a.port)))
