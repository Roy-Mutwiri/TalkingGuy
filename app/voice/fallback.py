"""FallbackSpeaker: use the online voice, and if it fails, speak the same text with the
local voice so a 24/7 stream never goes silent. After repeated failures it stays on the
local voice for a while before trying the online one again.
"""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Callable

log = logging.getLogger("voice")


class FallbackSpeaker:
    def __init__(self, primary, secondary_factory: Callable[[], object], cooloff_s: int = 600, max_failures: int = 3) -> None:
        self.primary = primary
        self._secondary_factory = secondary_factory
        self._secondary = None
        self.cooloff_s = cooloff_s
        self.max_failures = max_failures
        self.failures = 0
        self.primary_disabled_until = 0.0
        self.voice = getattr(primary, "voice", "?")

    @property
    def mood(self):
        return getattr(self.primary, "mood", "teach")

    @mood.setter
    def mood(self, value):
        for sp in (self.primary, self._secondary):
            if sp is not None and hasattr(sp, "mood"):
                sp.mood = value

    @property
    def expressive(self) -> bool:
        return bool(getattr(self.active, "expressive", False))

    @property
    def secondary(self):
        if self._secondary is None:
            log.warning("loading fallback voice (local Kokoro)")
            self._secondary = self._secondary_factory()
        return self._secondary

    @property
    def active(self):
        return self.secondary if time.time() < self.primary_disabled_until else self.primary

    def stop(self) -> None:
        for sp in (self.primary, self._secondary):
            if sp is not None:
                try:
                    sp.stop()
                except Exception:  # noqa: BLE001
                    pass

    @property
    def out_rate(self) -> int:
        return getattr(self.active, "out_rate", 48000)

    async def play_audio(self, audio, label: str = ""):
        sp = self.active
        if hasattr(sp, "play_audio"):
            async for ev in sp.play_audio(audio, label):
                yield ev

    def prefetch(self, text: str) -> None:
        sp = self.active
        if hasattr(sp, "prefetch"):
            sp.prefetch(text)

    async def speak(self, text: str) -> AsyncIterator[dict]:
        sp = self.active
        spoke = False
        failed = False
        async for ev in sp.speak(text):
            if ev["event"] == "sentence":
                spoke = True
            if ev["event"] == "error":
                failed = True
                continue
            if ev["event"] == "done" and failed and not spoke and sp is self.primary:
                break
            yield ev
        if sp is self.primary:
            if failed and not spoke:
                self.failures += 1
                log.warning("online voice failed (%d/%d); using local voice for this utterance", self.failures, self.max_failures)
                if self.failures >= self.max_failures:
                    self.primary_disabled_until = time.time() + self.cooloff_s
                    self.failures = 0
                    log.warning("online voice disabled for %d s", self.cooloff_s)
                async for ev in self.secondary.speak(text):
                    yield ev
            elif not failed:
                self.failures = 0

    async def say(self, text: str) -> None:
        async for _ in self.speak(text):
            pass
