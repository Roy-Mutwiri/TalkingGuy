"""Glitch-free audio output: a callback-driven stream fed from a ring buffer, plus the
shared "play a queue of sentences" loop used by every voice engine.

Blocking `stream.write()` with small chunks starves the device whenever the Python
thread is busy (GPU synthesis, the phonemizer, JSON over WebSockets...), which the
listener hears as crackle. PortAudio's callback runs on its own high-priority thread
and only copies from a pre-filled buffer, so it keeps going while Python stalls.

NOTE: open the RingPlayer from the main thread. WASAPI callback streams fail with a
WDM-KS error when opened from a worker thread on Windows.
"""
from __future__ import annotations

import queue
import threading
import time
import logging

import numpy as np
import sounddevice as sd


log = logging.getLogger("voice")


class RingPlayer:
    def __init__(self, samplerate: int, device: int | None, prebuffer_s: float = 0.30, capacity_s: float = 60.0) -> None:
        self.rate = samplerate
        self.device = device
        self.prebuffer = int(samplerate * prebuffer_s)
        self.rearm_prebuffer = int(samplerate * 0.08)   # after a mid-utterance drain, wait only briefly
        self.need = self.prebuffer
        self.buf = np.zeros(int(samplerate * capacity_s), dtype=np.float32)
        self.cap = self.buf.size
        self.w = 0          # total samples written by the producer
        self.r = 0          # total samples consumed by the callback
        self.lock = threading.Lock()
        self.underruns = 0
        self.gate = False
        self.flushed = False
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                self.stream = sd.OutputStream(samplerate=samplerate, channels=1, dtype="float32", device=device,
                                              blocksize=0, latency=0.2, callback=self._cb)
                self.stream.start()
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001  (PortAudio can fail transiently right after another stream closed)
                last_exc = exc
                time.sleep(0.4 * (attempt + 1))
        if last_exc is not None:
            raise last_exc

    # -- callback thread ----------------------------------------------------
    def _cb(self, out, frames, _time, status):
        if status.output_underflow:
            self.underruns += 1
        with self.lock:
            avail = self.w - self.r
            if not self.gate:
                if avail >= self.need or (self.flushed and avail > 0):
                    self.gate = True
                else:
                    out[:, 0] = np.random.standard_normal(frames).astype(np.float32) * 0.00006   # studio silence: effectively off, never a dead digital zero
                    return
            n = min(frames, avail)
            if n > 0:
                start = self.r % self.cap
                end = start + n
                if end <= self.cap:
                    out[:n, 0] = self.buf[start:end]
                else:
                    k = self.cap - start
                    out[:k, 0] = self.buf[start:]
                    out[k:n, 0] = self.buf[: n - k]
                self.r += n
            if n < frames:
                out[n:, 0] = np.random.standard_normal(frames - n).astype(np.float32) * 0.0012
                if avail == 0:
                    self.gate = False            # ran dry: re-arm a short prebuffer
                    self.need = self.rearm_prebuffer

    # -- producer thread ----------------------------------------------------
    def free(self) -> int:
        with self.lock:
            return self.cap - (self.w - self.r)

    def position(self) -> int:
        """Samples actually sent to the device so far."""
        with self.lock:
            return self.r

    def written(self) -> int:
        with self.lock:
            return self.w

    def write(self, audio: np.ndarray, stop: threading.Event | None = None) -> None:
        """Append audio, blocking while the ring is full."""
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        i = 0
        while i < audio.size:
            if stop is not None and stop.is_set():
                return
            room = self.free()
            if room <= 0:
                time.sleep(0.01)
                continue
            n = min(room, audio.size - i)
            with self.lock:
                start = self.w % self.cap
                end = start + n
                if end <= self.cap:
                    self.buf[start:end] = audio[i:i + n]
                else:
                    k = self.cap - start
                    self.buf[start:] = audio[i:i + k]
                    self.buf[: n - k] = audio[i + k:i + n]
                self.w += n
            i += n

    def begin_utterance(self) -> None:
        with self.lock:
            self.flushed = False
            self.gate = False
            self.need = self.prebuffer

    def flush_end(self) -> None:
        """Play out whatever is buffered even if it is below the prebuffer."""
        with self.lock:
            self.flushed = True

    def wait_drained(self, stop: threading.Event | None = None, timeout: float = 120.0) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if stop is not None and stop.is_set():
                return
            with self.lock:
                if self.w - self.r <= 0:
                    return
            time.sleep(0.01)

    def drop_pending(self) -> None:
        with self.lock:
            self.r = self.w

    def close(self) -> None:
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:  # noqa: BLE001
            pass


def play_queue(player: RingPlayer, audio_q: "queue.Queue", stop: threading.Event, emit, rate: int, chunk_n: int,
               gain: float, producer_alive) -> None:
    """Consumer loop shared by the engines: pull (sentence, audio) items until None, stream
    them into the ring, and emit sentence/level events in time with actual playback."""
    player.begin_utterance()
    first = True
    while True:
        t_wait = time.time()
        item = audio_q.get()
        waited = time.time() - t_wait
        if not first and waited > 0.25:
            log.info("voice underrun: next sentence arrived %.1fs late", waited)
        first = False
        if item is None:
            break
        s, a = item[0], item[1]
        if stop.is_set() or a.size == 0:
            continue
        a = np.asarray(a, dtype=np.float32) * gain
        duration_ms = int(a.size / rate * 1000)
        emit({"event": "sentence", "text": s, "duration_ms": duration_ms})
        base = player.written()
        player.write(a, stop)
        for i in range(0, a.size, chunk_n):
            if stop.is_set():
                player.drop_pending()
                break
            chunk = a[i:i + chunk_n]
            rms = float(np.sqrt(np.mean(chunk * chunk))) if chunk.size else 0.0
            emit({"event": "level", "level": min(1.0, rms * 6.0)})
            target = min(base + i + chunk_n, base + a.size)
            deadline = time.time() + chunk_n / rate * 4 + 1.0
            while player.position() < target and not stop.is_set() and time.time() < deadline:
                time.sleep(0.005)
    player.flush_end()
    player.wait_drained(stop)
    if player.underruns:
        emit({"event": "warning", "warning": f"audio underruns: {player.underruns}"})
        player.underruns = 0
    # drain anything the producer still pushes after an abort
    while True:
        try:
            if audio_q.get_nowait() is None:
                break
        except queue.Empty:
            if not producer_alive():
                break
            time.sleep(0.05)
