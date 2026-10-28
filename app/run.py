"""One-process launcher: hub (FastAPI/uvicorn) + director.

    .venv\\Scripts\\python -m app.run                 # full mode (needs ANTHROPIC_API_KEY in .env)
    .venv\\Scripts\\python -m app.run --offline       # template lessons, no Claude calls
    .venv\\Scripts\\python -m app.run --no-voice      # captions only (no audio device)

The stage and console open in our own windows: python -m app.stage_window [--console] (see supervise.ps1).
For 24/7 operation run supervise.ps1 instead, which restarts this on any failure.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import logging.handlers
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def build_speaker():
    """Online voice first, local voice as automatic fallback (24/7 streams must never go silent)."""
    from .voice import make_speaker
    from .voice.fallback import FallbackSpeaker

    engine = os.getenv("TTS_ENGINE", "edge").lower()
    if engine == "kokoro":
        return make_speaker("kokoro")
    if engine == "chatterbox":
        primary = make_speaker("chatterbox")
        primary.warm()                                   # load the model while the hub starts
        return FallbackSpeaker(primary, lambda: make_speaker("edge"))
    primary = make_speaker("edge")
    return FallbackSpeaker(primary, lambda: make_speaker("kokoro"))


async def main(args) -> None:
    from .brain.curriculum import Curriculum
    from .brain.memory import TeacherMemory
    from .chat.tiktok_reader import ChatReader
    from .data.quotes import QuoteService
    from .data.service import DataService
    from .director import Director

    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=args.port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    data = DataService()
    quotes = QuoteService(data=data)
    quotes_task = asyncio.create_task(quotes.run())
    curriculum = Curriculum()
    memory = TeacherMemory()
    planner = responder = None
    backend = os.getenv("BRAIN_BACKEND", "api").strip().lower()
    offline = args.offline or not (os.getenv("ANTHROPIC_API_KEY") or backend == "claude_code")
    if not offline:
        from .brain.client import get_client
        from .brain.planner import LessonPlanner
        from .brain.responder import ChatResponder

        client = get_client(backend=backend)
        planner = LessonPlanner(client, curriculum, data, memory=memory)
        responder = ChatResponder(client, memory=memory)
    else:
        logging.getLogger("run").warning("OFFLINE mode: template lessons, canned chat replies (set ANTHROPIC_API_KEY, or BRAIN_BACKEND=claude_code with a logged-in Claude Code, to enable the brain)")

    speaker = None
    if not args.no_voice:
        speaker = build_speaker()  # built on the main thread: WASAPI callback streams fail from worker threads

    music = None
    if speaker is not None:
        try:
            from .voice.kokoro_tts import find_output_device
            from .voice.music import MusicBed

            music = MusicBed("music", device_index=find_output_device(os.getenv("AUDIO_DEVICE", "CABLE Input")),
                             level=float(os.getenv("MUSIC_LEVEL", "0.14")))
            if not music.enabled:
                music = None
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("run").warning("music bed unavailable: %s", exc)

    chat = ChatReader()
    director = Director(f"ws://127.0.0.1:{args.port}/ws/control", data, curriculum, planner, responder, speaker, chat,
                        offline=offline, memory=memory, quotes=quotes, music=music)
    await asyncio.sleep(0.8)  # let uvicorn bind
    try:
        await director.run()
    finally:
        quotes_task.cancel()
        server.should_exit = True
        await server_task


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args()
    Path("logs").mkdir(exist_ok=True)
    handlers = [logging.StreamHandler(),
                logging.handlers.RotatingFileHandler("logs/stream.log", maxBytes=20_000_000, backupCount=5, encoding="utf-8")]
    logging.basicConfig(level=a.log, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    for noisy in ("httpx", "httpx2", "httpcore", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        asyncio.run(main(a))
    except KeyboardInterrupt:
        pass
