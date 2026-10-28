"""Background music bed, mixed into the same virtual cable as the voice, with ducking.

Put files you have the rights to in the `music/` folder (mp3/wav/flac/ogg/m4a):
  - tracks you generated yourself (scripts/make_music.py produces original beats locally), or
  - tracks from a library whose license explicitly covers TikTok LIVE streaming.
Never commercial songs: TikTok mutes/ends LIVEs that play copyrighted music, remixed or not.

The bed loops shuffled tracks at a low level and ducks under the voice. Only the folder, nothing from the internet.
The folder is rescanned as it plays: beats the live maker (music_maker.py) adds join the rotation, retired ones drop out,
and nothing repeats until every track has had its turn.
"""
from __future__ import annotations

import logging
import os
import random
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

log = logging.getLogger("music")
EXTS = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac")


def _decode(path: Path, rate: int) -> np.ndarray:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(rate), "pipe:1"],
                       capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="ignore")[:200])
    a = np.frombuffer(p.stdout, dtype=np.float32).copy()
    peak = float(np.abs(a).max()) if a.size else 0.0
    return a / peak * 0.9 if peak > 0 else a


class MusicBed:
    def __init__(self, folder: str | Path = "music", device_index: int | None = None, rate: int = 48000,
                 level: float = 0.14, duck_level: float = 0.035) -> None:
        import sounddevice as sd

        self.folder = Path(folder)
        self.rate = rate
        self.level = level
        self.duck_level = duck_level
        self.target_gain = level
        self.gain = 0.0
        self.tracks = sorted(p for p in self.folder.glob("*") if p.suffix.lower() in EXTS) if self.folder.exists() else []
        self.current: np.ndarray | None = None
        self.pos = 0
        self.now_playing = ""
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.enabled = bool(self.tracks)
        if not self.enabled:
            log.info("music bed disabled (no files in %s)", self.folder)
            return
        self.stream = sd.OutputStream(samplerate=rate, channels=1, dtype="float32", device=device_index, blocksize=0, latency=0.2, callback=self._cb)
        threading.Thread(target=self._loader, daemon=True).start()
        self.stream.start()
        log.info("music bed on: %d tracks", len(self.tracks))

    def _scan(self) -> list[Path]:
        try:
            return sorted(p for p in self.folder.glob("*") if p.suffix.lower() in EXTS and ".part" not in p.name)
        except OSError:
            return self.tracks

    def _loader(self) -> None:
        order = self.tracks[:]
        random.shuffle(order)
        played: set[Path] = set()
        last_scan = 0.0
        while not self._stop.is_set():
            with self._lock:
                need = self.current is None or self.pos >= self.current.size - self.rate
            if time.time() - last_scan > 30:
                last_scan = time.time()
                fresh = self._scan()
                new = [p for p in fresh if p not in order and p not in played]
                if new:
                    random.shuffle(new)
                    order.extend(new)                     # new beats join the current pass
                    self.tracks = fresh
                    log.info("music: %d new track(s) joined the rotation (%d total)", len(new), len(fresh))
                order = [p for p in order if p.exists()]   # retired beats leave
            if need:
                if not order:                              # everyone has played: shuffle a new pass from the folder
                    order = [p for p in self._scan()]
                    random.shuffle(order)
                    played.clear()
                    if not order:
                        time.sleep(2)
                        continue
                path = order.pop(0)
                played.add(path)
                try:
                    audio = _decode(path, self.rate)
                    with self._lock:
                        self.current, self.pos, self.now_playing = audio, 0, path.stem
                    log.info("music: %s (%.0fs)", path.stem, audio.size / self.rate)
                except Exception as exc:  # noqa: BLE001
                    log.warning("music decode failed %s: %s", path.name, exc)
                    time.sleep(1)
            time.sleep(0.5)

    def _cb(self, out, frames, _t, status):
        with self._lock:
            cur, pos = self.current, self.pos
            if cur is None or pos >= cur.size:
                out.fill(0)
                return
            n = min(frames, cur.size - pos)
            chunk = cur[pos:pos + n]
            # smooth gain ramp toward the target (ducking)
            g0, g1 = self.gain, self.target_gain
            ramp = np.linspace(g0, g1, n, dtype=np.float32) if abs(g1 - g0) > 1e-4 else np.full(n, g1, dtype=np.float32)
            out[:n, 0] = chunk * ramp
            if n < frames:
                out[n:, 0] = 0
            self.pos = pos + n
            self.gain = float(ramp[-1])

    def duck(self, speaking: bool) -> None:
        if not self.enabled:
            return
        self.target_gain = self.duck_level if speaking else self.level

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(0.5, level))
        if self.target_gain > self.duck_level:
            self.target_gain = self.level

    def skip(self) -> None:
        with self._lock:
            if self.current is not None:
                self.pos = self.current.size

    def close(self) -> None:
        self._stop.set()
        if self.enabled:
            try:
                self.stream.stop(); self.stream.close()
            except Exception:  # noqa: BLE001
                pass
