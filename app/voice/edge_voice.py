"""Online neural voice via Microsoft Edge's public text-to-speech service (edge-tts).
Free, no API key, very natural voices. Same interface as kokoro_tts.Speaker, same
RingPlayer playback into the virtual cable.

Voices worth trying (TTS_VOICE):
  en-US-AndrewMultilingualNeural  warm, confident male (default)
  en-US-BrianMultilingualNeural   casual male
  en-US-GuyNeural                 news-style male
  en-US-AvaMultilingualNeural     bright female
  en-GB-RyanNeural                British male
  en-KE-ChilembaNeural            Kenyan English male
"""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import subprocess
import threading
import time
from collections import OrderedDict
from typing import AsyncIterator

import numpy as np

from .kokoro_tts import find_output_device, split_sentences
from .humanize_audio import humanize_sentence
from .human import TalkClock, describe, plan_sentence
from . import sfx
from .player import play_queue

log = logging.getLogger("voice")

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"
FETCH_TIMEOUT_S = 25


def _decode_mp3(data: bytes, rate: int) -> np.ndarray:
    """MP3 bytes -> float32 mono at `rate` using ffmpeg."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(rate), "pipe:1"],
        input=data, capture_output=True, check=False,
    )
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {p.stderr.decode(errors='ignore')[:200]}")
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


_ctx = threading.local()      # per-thread: True inside the producer of the line being spoken


def _seed(sentence: str) -> int:
    """Stable per-sentence seed for the humanizer (same text -> same breath and gaps -> same clip)."""
    import zlib

    return zlib.crc32(sentence.encode("utf-8")) & 0x7FFFFFFF


class EdgeSpeaker:
    engine = "edge"                 # Edge sets pace itself (SSML rate); local engines get it from the human layer
    plan_override: dict | None = None   # one-shot delivery override for the next speak() (e.g. {"murmur": True})

    def __init__(self, voice: str | None = None, device: str | None = None, rate: str = "+0%") -> None:
        import sounddevice as sd

        self.clock = TalkClock()
        self.rtf = 0.35                 # synthesis seconds per audio second (Edge: network); local engines measure their own
        self.voice = voice or os.getenv("TTS_VOICE") or DEFAULT_VOICE
        if "-" not in self.voice:
            self.voice = DEFAULT_VOICE  # a Kokoro voice id was left in .env
        self.rate_opt = rate
        self.mood = "teach"
        self.device_index = find_output_device(device if device is not None else os.getenv("AUDIO_DEVICE", "CABLE Input"))
        try:
            dev = sd.query_devices(self.device_index if self.device_index is not None else sd.default.device[1])
            self.out_rate = int(dev.get("default_samplerate") or 48000)
        except Exception:  # noqa: BLE001
            self.out_rate = 48000
        self.out_chunk = int(self.out_rate * 0.05)
        self.gain = float(os.getenv("TTS_GAIN", "0.8"))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._ring = None
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._inflight: set[str] = set()
        try:
            self._player()
        except Exception as exc:  # noqa: BLE001
            log.warning("could not open audio output yet (%s); will retry on first speech", exc)
        log.info("Edge TTS ready, voice=%s, output %d Hz", self.voice, self.out_rate)

    def _player(self):
        if self._ring is None:
            from .player import RingPlayer

            self._ring = RingPlayer(self.out_rate, self.device_index)
        return self._ring

    def stop(self) -> None:
        self._stop.set()

    # ---- synthesis -----------------------------------------------------------
    # ---- intonation ----------------------------------------------------------
    # (rate %, pitch Hz) baselines. Upbeat 7/10 by default; "excited" is the brief lift when something real happens,
    # "considerate" is the drop when a viewer describes a loss. Every label here changes the delivered audio.
    MOODS = {"teach": (6, 2), "show": (10, 4), "hype": (14, 7), "calm": (-4, -2), "serious": (-3, -3), "warm": (3, 3),
             "cheerful": (9, 5), "excited": (17, 10), "curious": (4, 5), "considerate": (-7, -3)}

    def prosody(self, sentence: str) -> tuple[str, str]:
        """Rate/pitch for one sentence: mood baseline + punctuation/content cues + a little
        deterministic variation so two sentences never sound identical."""
        import zlib

        rate, pitch = self.MOODS.get(self.mood, (4, 0))
        st = sentence.strip()
        low = st.lower()
        words = len(st.split())
        if st.endswith("?"):
            pitch += 3
        if self.mood in ("cheerful", "excited", "show", "hype") and words <= 4:
            pitch += 3                                   # quick, bright reactions ("Love it." "Okay!")
        if self.mood in ("show", "excited", "hype") and st.endswith("!"):
            rate += 3; pitch += 2                        # exclamations really land
        if self.mood == "considerate":
            rate -= 2 if words >= 12 else 0              # patient, unhurried
        if st.endswith("!"):
            rate += 6; pitch += 4
        if any(k in low for k in ("watch this", "look at", "see that", "right here", "this is the part")):
            rate -= 7; pitch += 1
        if any(ch.isdigit() for ch in st):
            rate -= 3
        if words <= 5:
            rate -= 6
        elif words >= 24:
            rate += 3
        h = zlib.crc32(st.encode()) % 100
        rate += (h % 7) - 3
        pitch += (h // 7 % 5) - 2
        rate = max(-20, min(32, rate)); pitch = max(-12, min(18, pitch))
        return (f"{rate:+d}%", f"{pitch:+d}Hz")

    async def _fetch(self, text: str) -> np.ndarray:
        import edge_tts

        rate, pitch = self.prosody(text)
        last: Exception | None = None
        for attempt in range(3):
            try:
                comm = edge_tts.Communicate(text, self.voice, rate=rate, pitch=pitch)
                buf = bytearray()

                async def pull():
                    async for chunk in comm.stream():
                        if chunk["type"] == "audio":
                            buf.extend(chunk["data"])

                await asyncio.wait_for(pull(), timeout=FETCH_TIMEOUT_S)
                return await asyncio.to_thread(_decode_mp3, bytes(buf), self.out_rate)
            except Exception as exc:  # noqa: BLE001
                last = exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"edge-tts failed: {last}")

    def synth_many(self, sentences: list[str]) -> list[np.ndarray]:
        """Fetch all sentences concurrently (one event loop in the calling thread); cached."""
        todo = []
        with self._cache_lock:
            for s in sentences:
                if s not in self._cache and s not in self._inflight:
                    self._inflight.add(s)
                    todo.append(s)
        # a mood change invalidates cached deliveries
        if getattr(self, "_cache_mood", None) != self.mood:
            with self._cache_lock:
                self._cache.clear()
            self._cache_mood = self.mood

        async def run_all():
            return await asyncio.gather(*(self._fetch(s) for s in todo), return_exceptions=True)

        results = asyncio.run(run_all()) if todo else []
        with self._cache_lock:
            for s, r in zip(todo, results):
                self._inflight.discard(s)
                if isinstance(r, np.ndarray):
                    self._cache[s] = r
                    while len(self._cache) > 200:
                        self._cache.popitem(last=False)
                else:
                    log.warning("edge-tts failed for %r: %s", s[:40], r)
        # wait briefly for sentences another thread is fetching (prefetch)
        out = []
        for s in sentences:
            deadline = time.time() + FETCH_TIMEOUT_S * 3
            while True:
                with self._cache_lock:
                    a = self._cache.get(s)
                    pending = s in self._inflight
                if a is not None or not pending or time.time() > deadline:
                    break
                time.sleep(0.05)
            out.append(a if a is not None else np.zeros(0, dtype=np.float32))
        return out

    def synth(self, text: str) -> np.ndarray:
        parts = self.synth_many(split_sentences(text))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def prefetch(self, text: str) -> None:
        """Warm the synthesis cache for a future utterance in a background thread (no audio), so the line
        plays the instant it is called for."""
        sentences = split_sentences(text)
        if not sentences:
            return

        def work() -> None:
            try:
                for s_ in sentences:
                    self.synth_many([s_])
            except Exception as exc:  # noqa: BLE001
                log.warning("prefetch failed: %s", exc)

        threading.Thread(target=work, daemon=True).start()

    # ---- playback --------------------------------------------------------------
    async def play_audio(self, audio: np.ndarray, label: str = "") -> AsyncIterator[dict]:
        """Play a ready clip (a recorded murmur, a laugh) through the same player, with the same level events."""
        if audio is None or audio.size == 0:
            return
        self._stop.clear()
        loop = asyncio.get_running_loop()
        events: asyncio.Queue = asyncio.Queue()
        audio_q: queue.Queue = queue.Queue()
        emit = lambda ev: loop.call_soon_threadsafe(events.put_nowait, ev)  # noqa: E731
        audio_q.put((label, np.asarray(audio, dtype=np.float32)))
        audio_q.put(None)

        def consumer():
            try:
                with self._lock:
                    play_queue(self._player(), audio_q, self._stop, emit, self.out_rate, self.out_chunk, self.gain, lambda: False)
            except Exception as exc:  # noqa: BLE001
                emit({"event": "error", "error": str(exc)})
            finally:
                emit({"event": "done"})

        threading.Thread(target=consumer, daemon=True).start()
        while True:
            ev = await events.get()
            yield ev
            if ev["event"] == "done":
                break

    async def speak(self, text: str) -> AsyncIterator[dict]:
        sentences = split_sentences(text)
        if not sentences:
            return
        # the host's own recorded laughs / sighs stand in for tags at the edges of a sentence
        edges: list[tuple[list[str], list[str]]] = []
        if sfx.available() and getattr(self, "expressive", False):
            stripped = []
            for s in sentences:
                lead, body, tail = sfx.split_edge_tags(s)
                if body:
                    stripped.append(body); edges.append((lead, tail))
                else:
                    stripped.append(s); edges.append(([], []))
            sentences = stripped
        else:
            edges = [([], []) for _ in sentences]
        self._stop.clear()
        loop = asyncio.get_running_loop()
        events: asyncio.Queue = asyncio.Queue()
        audio_q: queue.Queue = queue.Queue()
        emit = lambda ev: loop.call_soon_threadsafe(events.put_nowait, ev)  # noqa: E731

        def _urgent(fn):
            # mark this thread as the line being spoken: its synthesis goes ahead of any prefetch
            def run():
                _ctx.urgent = True
                self._urgent_count = getattr(self, "_urgent_count", 0) + 1
                try:
                    return fn()
                finally:
                    self._urgent_count = max(0, getattr(self, "_urgent_count", 1) - 1)
                    _ctx.urgent = False
            return run

        override, self.plan_override = self.plan_override, None
        mood_now = self.mood
        engine_rate = self.engine == "edge"

        def deliver(i: int, s: str, a: np.ndarray, prev_len: int) -> np.ndarray:
            rng = np.random.default_rng(_seed(s))
            plan = plan_sentence(s, mood=mood_now, index=i, total=len(sentences), rng=rng, clock=self.clock,
                                 engine_sets_rate=engine_rate, override=override)
            out = humanize_sentence(a, self.out_rate, first=i == 0, long_prev=prev_len > 90, mood=mood_now, seed=_seed(s), plan=plan)
            lead, tail = edges[i] if i < len(edges) else ([], [])
            if a.size and (lead or tail):
                parts = []
                for fam in lead:
                    clip = sfx.get(fam, self.out_rate)
                    if clip is not None:
                        parts.append(clip)
                parts.append(out)
                for fam in tail:
                    clip = sfx.get(fam, self.out_rate)
                    if clip is not None:
                        parts.append(clip)
                out = sfx.join(parts, self.out_rate, 0.09)
            if a.size:
                self.clock.note(out.size / self.out_rate)
                log.debug("delivery: %s | %s", describe(plan), s[:60])
            return out

        def producer():
            try:
                # first sentence alone (fastest first audio), the rest concurrently
                first = _urgent(lambda: self.synth_many(sentences[:1]))()
                rest_thread = None
                rest: list[np.ndarray] = []
                if len(sentences) > 1:
                    rest_thread = threading.Thread(target=_urgent(lambda: rest.extend(self.synth_many(sentences[1:]))), daemon=True)
                    rest_thread.start()
                a0 = deliver(0, sentences[0], first[0], 0)
                if rest_thread:
                    # fluency: when the engine is slower than playback, hold the first sentence briefly so the rest gets
                    # ahead; a short delay before a line beats a stall in the middle of it. Cached lines never wait.
                    with self._cache_lock:
                        pending = [s for s in sentences[1:] if s not in self._cache]
                    words_left = sum(len(s.split()) for s in pending)
                    need = self.rtf * (words_left / 2.6) - a0.size / self.out_rate
                    if pending and need > 0.3:
                        rest_thread.join(timeout=min(need, 3.5))
                audio_q.put((sentences[0], a0))
                if rest_thread:
                    rest_thread.join()
                    prev_len = len(sentences[0])
                    for i, (s, a) in enumerate(zip(sentences[1:], rest), start=1):
                        if self._stop.is_set():
                            break
                        ah = deliver(i, s, a, prev_len)
                        audio_q.put((s, ah))
                        prev_len = len(s)
            except Exception as exc:  # noqa: BLE001
                log.exception("synthesis failed")
                emit({"event": "error", "error": str(exc)})
            finally:
                audio_q.put(None)

        def consumer():
            try:
                with self._lock:
                    play_queue(self._player(), audio_q, self._stop, emit, self.out_rate, self.out_chunk, self.gain, prod.is_alive)
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
        async for _ in self.speak(text):
            pass
