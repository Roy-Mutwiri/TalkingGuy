import math
import random
import time

import numpy as np

from app.brain.schema import LessonScript, Beat, ZoneAction, FibAction, NoteAction, PathAction, IndicatorAction, LoadAction
from app.data.analysis import analyze
from app.voice.disfluency import humanize_text
from app.voice.humanize_audio import humanize_sentence, breath, room_tone


def _series(n=200, seed=3):
    rnd = random.Random(seed)
    out, p, t = [], 2000.0, 1_700_000_000
    for i in range(n):
        drift = math.sin(i / 23) * 2.5
        o = p
        c = o + drift + rnd.gauss(0, 3)
        h = max(o, c) + abs(rnd.gauss(0, 2))
        lo = min(o, c) - abs(rnd.gauss(0, 2))
        out.append({"time": t + i * 900, "open": o, "high": h, "low": lo, "close": c, "volume": 100 + rnd.random() * 50})
        p = c
    return out


def test_analyze_produces_a_full_markup():
    steps = analyze(_series(), "XAU/USD")
    kinds = {s["action"] for s in steps}
    assert {"marker", "zone", "fib", "indicator", "hline", "note"} <= kinds, kinds
    assert len(steps) >= 12
    narrated = [s for s in steps if s.get("say")]
    assert len(narrated) >= 6
    for s in steps:
        for k in ("time", "t1", "t2"):
            if k in s:
                assert "T" in s[k]  # ISO strings
        if s["action"] == "indicator":
            assert len(s["points"]) >= 50


def test_analyze_handles_short_series():
    assert analyze(_series(20)) == []


def test_schema_accepts_new_actions():
    script = LessonScript(topic="t", module="m", summary="s", beats=[
        Beat(say="a", chart=[LoadAction(symbol="XAUUSD", tf="15m", start="2025-01-01", end="2025-01-03")]),
        Beat(say="b", chart=[ZoneAction(top=2010, bottom=2000, label="support"), FibAction(t1="2025-01-01T00:00", p1=1990, t2="2025-01-02T00:00", p2=2020)], deep=True),
        Beat(say="c", chart=[NoteAction(time="2025-01-02T00:00", price=2015, text="sweep"), PathAction(points=[{"time": "2025-01-01T00:00", "price": 1}, {"time": "2025-01-02T00:00", "price": 2}])]),
        Beat(say="d", chart=[IndicatorAction(name="EMA 20", points=[{"time": "2025-01-01T00:00", "value": 2000.0}])]),
    ])
    assert script.beats[1].deep is True


def test_humanize_text_is_light_and_skips_serious():
    s = "Price came back to support. Buyers stepped in there twice before. That is the level that matters."
    assert humanize_text(s, "serious") == s
    outs = {humanize_text(s, "teach", seed=i) for i in range(30)}
    assert len(outs) > 3  # varies
    for o in outs:
        assert "support" in o and "matters" in o
        assert len(o) < len(s) * 1.6


def test_humanize_audio_is_fast_and_sane():
    rate = 48000
    voice = (np.sin(np.linspace(0, 2 * np.pi * 220 * 4, rate * 4)) * 0.5).astype(np.float32)
    t0 = time.perf_counter()
    out = humanize_sentence(voice, rate, first=True, long_prev=False)
    dt = time.perf_counter() - t0
    assert dt < 0.5, f"too slow: {dt:.2f}s"
    assert out.size > voice.size and np.abs(out).max() <= 0.95
    assert np.abs(breath(rate)).max() < 0.1 and np.abs(room_tone(rate, 0.1)).max() < 0.01
    for n in (217727, 217728, 48001, 12345):   # odd lengths used to break the room-tone mix
        o = humanize_sentence((np.sin(np.linspace(0, 100, n)) * 0.4).astype(np.float32), rate, first=False, long_prev=True)
        assert o.size > n and not np.isnan(o).any()


def test_broadcast_chain_is_clean_and_consistent():
    import numpy as np
    from app.voice.humanize_audio import limiter, mic_chain, normalize, room_tone

    rate = 48000
    rng = np.random.default_rng(1)
    t = np.arange(rate * 2) / rate
    # a voiced-ish test signal with a loud burst and a quiet stretch
    sig = (np.sin(2 * np.pi * 140 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)) + 0.2 * rng.standard_normal(t.size)).astype(np.float32)
    sig[rate:rate + 2000] *= 3.0                       # a peak that would clip
    sig[int(rate * 1.5):] *= 0.15                      # a quiet tail
    out = mic_chain(sig, rate)
    assert out.shape == sig.shape and np.isfinite(out).all()
    assert np.abs(out).max() <= 10 ** (-1.0 / 20) + 1e-3    # limiter ceiling -1 dBFS, never clipped
    assert np.abs(limiter(np.full(1000, 2.0, dtype=np.float32), rate)).max() <= 10 ** (-1.0 / 20) + 1e-3
    lvl = 20 * np.log10(np.sqrt(np.mean(normalize(sig)[np.abs(normalize(sig)) > 0.01] ** 2)) + 1e-9)
    assert -22 < lvl < -12                               # normalised to broadcast level
    assert np.abs(room_tone(rate, 0.5)).max() < 0.001     # studio silence, not hiss
