"""English rising/falling intonation: the rulebook classifies as a native speaker would, and applying it keeps the voice."""
from __future__ import annotations

import numpy as np

from app.voice import intonation


def test_rulebook_patterns():
    c = intonation.classify
    assert c("Gold held the level twice.") == "fall"                               # statement
    assert c("Where would the idea be wrong?") == "fall"                           # wh-question
    assert c("Look at the close.") == "fall"                                       # command
    assert c("Do you see the second attempt?") == "rise"                           # yes/no question
    assert c("Can price trade through it?") == "rise"
    assert c("Four thousand?") == "rise"                                           # check / echo question
    assert c("That's the level, right?") == "tag"                                  # tag question
    assert c("Is it support or resistance?") == "alt"                              # alternatives
    assert c("First, the level held, second, no follow-through, third, the close is back inside.") == "list"
    assert c("If price trades through it,", 0, 3) == "rise"                        # unfinished thought
    assert c("The push had no follow-through and", 0, 3) == "rise"                 # hands over to the next sentence
    assert c("It might hold here, usually it does.") == "fall_rise"                # hedge
    assert c("Look at that!") == "rise_fall"                                       # surprise
    assert c("Whoa, there it is.") == "rise_fall"
    assert c("[laugh] Maria, good one.") == "fall"                                 # tags ignored


def _voice(rate: int, seconds: float, hz: float = 130.0) -> np.ndarray:
    """A vowel-like signal: a harmonic series with a spectral envelope, so the vocoder tracks it like speech."""
    t = np.arange(int(rate * seconds)) / rate
    y = np.zeros_like(t)
    for k in range(1, 25):
        y += np.sin(2 * np.pi * hz * k * t) / (k ** 1.2) * (1.0 if k < 6 else 0.4)
    y *= 0.2 * (0.7 + 0.3 * np.sin(2 * np.pi * 2.0 * t))
    return y.astype(np.float32)


def _f0(y: np.ndarray, rate: int) -> float:
    import pyworld as pw

    f0, t = pw.dio(y.astype(np.float64), rate, frame_period=5.0)
    f0 = pw.stonemask(y.astype(np.float64), f0, t, rate)
    v = f0[f0 > 0]
    return float(np.median(v)) if v.size else 0.0


def test_rise_rises_and_fall_falls_without_changing_the_voice():
    rate = 24000
    y = _voice(rate, 2.0)
    rise = intonation.apply(y, rate, "rise", 1.0)
    fall = intonation.apply(y, rate, "fall", 1.0)
    assert rise.size == y.size and fall.size == y.size
    assert np.isfinite(rise).all() and np.isfinite(fall).all()
    head, tail = slice(0, rate // 2), slice(-rate // 2, None)
    assert _f0(rise[tail], rate) > _f0(rise[head], rate) * 1.06          # a yes/no question ends higher
    assert _f0(fall[tail], rate) < _f0(fall[head], rate) * 0.97          # a statement ends lower
    # the voice stays the same person: spectral shape barely moves (resampling would move it a lot)
    import librosa

    m0 = librosa.feature.mfcc(y=y, sr=rate, n_mfcc=13)[1:]
    m1 = librosa.feature.mfcc(y=rise, sr=rate, n_mfcc=13)[1:]
    assert float(np.mean(np.abs(m0 - m1))) < 8.0


def test_flat_and_short_inputs_pass_through():
    rate = 24000
    y = _voice(rate, 0.3)
    assert intonation.apply(y, rate, "fall", 1.0) is y
    assert intonation.apply(_voice(rate, 2.0), rate, "flat", 1.0).size == rate * 2
