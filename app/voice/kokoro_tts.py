"""Streaming text-to-speech with Kokoro-82M, played straight into an audio device
(normally the VB-Cable input, which TikTok LIVE Studio reads as a microphone).

Usage (async):
    speaker = Speaker()                       # loads the model once, picks the device
    async for ev in speaker.speak("Hello."):  # yields sentence + level events
        ...
    speaker.stop()                            # cut the current utterance (operator mute)

Events yielded by speak():
    {"event": "sentence", "text": str, "duration_ms": int}   just before a sentence starts playing
    {"event": "level", "level": float 0..1}                  ~20 times per second while audio plays
    {"event": "done"}                                        when the whole text has been played

Synthesis of sentence N+1 runs in a worker thread while sentence N is playing, so
there is no gap between sentences and first audio starts after a single short sentence.
"""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import re
import threading
import time
from typing import AsyncIterator

import numpy as np

from .player import play_queue

log = logging.getLogger("voice")

SAMPLE_RATE = 24000
CHUNK = 1200  # 50 ms at 24 kHz
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-Z0-9\"'(])")


def split_sentences(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_RE.split(text) if p.strip()]
    # merge very short fragments ("No.") into the previous sentence so Kokoro has context
    merged: list[str] = []
    for p in parts:
        if merged and len(p) < 12:
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def find_output_device(name_substring: str | None) -> int | None:
    import sounddevice as sd

    if not name_substring:
        return None
    needle = name_substring.lower()
    best = None
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_output_channels", 0) > 0 and needle in dev["name"].lower():
            api = sd.query_hostapis(dev["hostapi"])["name"]
            # prefer WASAPI over MME/DirectSound for lower latency and exact sample rate handling
            score = 2 if "WASAPI" in api else 1
            if best is None or score > best[0]:
                best = (score, idx, dev["name"], api)
    if best:
        log.info("audio output: [%d] %s (%s)", best[1], best[2], best[3])
        return best[1]
    log.warning("audio device containing %r not found; using default output", name_substring)
    return None


class Speaker:
    def __init__(self, voice: str | None = None, device: str | None = None, speed: float = 1.0, lang_code: str = "a") -> None:
        from kokoro import KPipeline  # heavy import, done here on purpose

        self.mood = "teach"
        self.voice = voice or os.getenv("TTS_VOICE", "am_michael")
        if "-" in self.voice:
            self.voice = "am_michael"  # an Edge voice name is set in .env; Kokoro ids look like am_michael
        self.speed = speed
        self.device_index = find_output_device(device if device is not None else os.getenv("AUDIO_DEVICE", "CABLE Input"))
        self._pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")
        self._stop = threading.Event()
        self._lock = threading.Lock()
        # WASAPI shared-mode devices only accept their configured rate (usually 44.1/48 kHz),
        # so we open the stream at the device rate and resample Kokoro's 24 kHz output.
        import sounddevice as sd

        try:
            dev = sd.query_devices(self.device_index if self.device_index is not None else sd.default.device[1])
            self.out_rate = int(dev.get("default_samplerate") or SAMPLE_RATE)
        except Exception:  # noqa: BLE001
            self.out_rate = SAMPLE_RATE
        self.out_chunk = int(self.out_rate * 0.05)
        self.gain = float(os.getenv("TTS_GAIN", "0.8"))   # headroom so downstream mic chains never clip
        self._ring = None
        try:
            self._player()   # open the device from the main thread; WASAPI is picky about which thread opens it
        except Exception as exc:  # noqa: BLE001
            log.warning("could not open audio output yet (%s); will retry on first speech", exc)
        log.info("Kokoro ready, voice=%s, output %d Hz", self.voice, self.out_rate)

    def _player(self):
        """Lazily open one persistent callback-driven output stream (see player.py)."""
        if self._ring is None:
            from .player import RingPlayer

            self._ring = RingPlayer(self.out_rate, self.device_index)
        return self._ring

    def _to_device_rate(self, audio: np.ndarray) -> np.ndarray:
        if self.out_rate == SAMPLE_RATE or audio.size == 0:
            return audio
        n_out = int(audio.size * self.out_rate / SAMPLE_RATE)
        x_old = np.linspace(0.0, 1.0, audio.size, endpoint=False)
        x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
        return np.interp(x_new, x_old, audio).astype(np.float32)

    # ---- synthesis -------------------------------------------------------
    def synth(self, text: str) -> np.ndarray:
        """Synthesize one sentence to float32 mono at 24 kHz."""
        chunks = []
        for _gs, _ps, audio in self._pipeline(text, voice=self.voice, speed=self.speed):
            if audio is None:
                continue
            a = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
            chunks.append(a.astype(np.float32))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        out = np.concatenate(chunks)
        peak = float(np.max(np.abs(out))) if out.size else 0.0
        if peak > 1.0:
            out = out / peak
        return out

    # ---- playback --------------------------------------------------------
    def stop(self) -> None:
        """Abort whatever is currently being spoken."""
        self._stop.set()

    async def speak(self, text: str) -> AsyncIterator[dict]:
        sentences = split_sentences(text)
        if not sentences:
            return
        self._stop.clear()
        loop = asyncio.get_running_loop()
        events: asyncio.Queue = asyncio.Queue()
        audio_q: queue.Queue = queue.Queue(maxsize=2)
        resampled_q = audio_q

        def producer():
            try:
                for s in sentences:
                    if self._stop.is_set():
                        break
                    t0 = time.perf_counter()
                    a = self.synth(s)
                    log.debug("synth %.0f ms for %d chars", (time.perf_counter() - t0) * 1000, len(s))
                    audio_q.put((s, self._to_device_rate(a)))
            except Exception as exc:  # surface errors to the consumer instead of hanging
                log.exception("synthesis failed")
                audio_q.put(("", np.zeros(0, dtype=np.float32)))
                loop.call_soon_threadsafe(events.put_nowait, {"event": "error", "error": str(exc)})
            finally:
                audio_q.put(None)

        def consumer():
            emit = lambda ev: loop.call_soon_threadsafe(events.put_nowait, ev)  # noqa: E731
            try:
                with self._lock:
                    play_queue(self._player(), resampled_q, self._stop, emit, self.out_rate, self.out_chunk, self.gain, prod.is_alive)
            except Exception as exc:  # noqa: BLE001
                log.exception("playback failed")
                emit({"event": "error", "error": str(exc)})
            finally:
                emit({"event": "done"})

        prod = threading.Thread(target=producer, daemon=True)
        cons = threading.Thread(target=consumer, daemon=True)
        prod.start()
        cons.start()
        while True:
            ev = await events.get()
            if ev["event"] == "warning":
                log.warning(ev["warning"])
                continue
            yield ev
            if ev["event"] == "done":
                break

    async def say(self, text: str) -> None:
        """Speak and ignore events (handy for tests)."""
        async for _ in self.speak(text):
            pass


def list_devices() -> str:
    import sounddevice as sd

    return str(sd.query_devices())
