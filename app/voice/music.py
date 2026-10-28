"""Background music bed, mixed into the same virtual cable as the voice, with ducking.

Put files you have the rights to in the `music/` folder (mp3/wav/flac/ogg/m4a):
  - tracks you generated yourself (scripts/make_music.py produces original beats locally), or
  - tracks from a library whose license explicitly covers TikTok LIVE streaming.
Never commercial songs: TikTok mutes/ends LIVEs that play copyrighted music, remixed or not.

The bed loops shuffled tracks at a low level and ducks under the voice.

Online mode (console toggle "Popular music"): instead of the folder, the bed plays what is trending on Audius
right now (app/voice/online_music.py), downloaded one track ahead so there is never a gap. Switch back and the
folder tracks resume. If the internet is down the folder plays until a download succeeds again.
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
        self.online = False                       # True: play trending online tracks instead of the folder
        self._online_src = None
        self._online_next: tuple[Path, str] | None = None
        self._online_fetching = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.enabled = True                       # the online mode works without local files; the folder may be empty
        if not self.tracks:
            log.info("music bed: no files in %s; only the online mode can play", self.folder)
        self.stream = sd.OutputStream(samplerate=rate, channels=1, dtype="float32", device=device_index, blocksize=0, latency=0.2, callback=self._cb)
        threading.Thread(target=self._loader, daemon=True).start()
        self.stream.start()
        log.info("music bed on: %d tracks", len(self.tracks))

    def _fetch_online(self) -> None:
        """Background: download the next trending track so it is on disk before the current one ends."""
        try:
            if self._online_src is None:
                from .online_music import OnlineMusic

                self._online_src = OnlineMusic()
            got = self._online_src.next_file()
            with self._lock:
                self._online_next = got
            if got is None:
                log.warning("music: online source gave nothing; the folder plays until it recovers")
        except Exception as exc:  # noqa: BLE001
            log.warning("music: online fetch failed: %s", exc)
        finally:
            self._online_fetching = False

    def _loader(self) -> None:
        order = self.tracks[:]
        random.shuffle(order)
        i = 0
        last_warn = 0.0
        wait_since = 0.0
        while not self._stop.is_set():
            with self._lock:
                need = self.current is None or self.pos >= self.current.size - self.rate
                online, have_next, fetching = self.online, self._online_next is not None, self._online_fetching
            if online and not have_next and not fetching:
                self._online_fetching = True
                threading.Thread(target=self._fetch_online, daemon=True).start()
            if need:
                path, label = None, ""
                if online:
                    with self._lock:
                        if not self.online:                     # switched off since the top of the loop
                            online, nxt = False, None
                        else:
                            nxt, self._online_next = self._online_next, None
                if online:
                    if nxt is not None:
                        path, label = nxt
                        wait_since = 0.0
                    else:
                        wait_since = wait_since or time.time()
                        if (self.current is not None and self.pos < self.current.size) or time.time() - wait_since < 12:
                            time.sleep(0.5)   # the download is on its way: a few seconds of quiet beat the wrong track
                            continue
                        if time.time() - last_warn > 30:
                            last_warn = time.time()
                            log.info("music: online track not ready; playing a folder track meanwhile")
                if path is None and order:
                    path = order[i % len(order)]
                    label = path.stem
                    i += 1
                if path is None:
                    time.sleep(1)
                    continue
                try:
                    audio = _decode(path, self.rate)
                    with self._lock:
                        self.current, self.pos, self.now_playing = audio, 0, label
                    log.info("music: %s (%.0fs)", label, audio.size / self.rate)
                except Exception as exc:  # noqa: BLE001
                    log.warning("music decode failed %s: %s", path.name, exc)
                    time.sleep(1)
            time.sleep(0.5)

    def set_online(self, on: bool) -> None:
        """Switch between the folder and the online trending chart; the change is heard at once."""
        on = bool(on)
        if on == self.online:
            return
        self.online = on
        if not on:
            with self._lock:
                self._online_next = None            # a track fetched meanwhile stays cached on disk for next time
        log.info("music: %s", "online trending tracks (Audius)" if on else "folder tracks")
        if on and not self._online_fetching and self._online_next is None:
            self._online_fetching = True
            threading.Thread(target=self._fetch_online, daemon=True).start()
        self.skip()

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
