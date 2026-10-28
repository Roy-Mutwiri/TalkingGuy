"""The human delivery layer: plans follow the cues, audio pieces are sane, slips are rare and rate-limited."""
from __future__ import annotations

import numpy as np

from app.voice import human
from app.voice.disfluency import Imperfections
from app.voice.humanize_audio import humanize_sentence


def _rng(seed=1):
    return np.random.default_rng(seed)


def test_plan_reads_risk_number_and_question_cues():
    risk = human.plan_sentence("The stop goes where the idea is wrong, below the low.", mood="teach", rng=_rng(), now=12 * 3600)
    assert "risk line" in risk.notes and risk.speed < 1.0 and risk.pre_gap >= 0.35
    num = human.plan_sentence("Gold is at 3,912 right now.", mood="teach", rng=_rng(), now=12 * 3600)
    assert "number" in num.notes and num.pre_gap > 0.15
    q = human.plan_sentence("Which detail would you check first?", mood="teach", rng=_rng(), now=12 * 3600)
    assert "question" in q.notes and q.post_gap >= 0.3


def test_aside_is_quicker_and_quieter():
    p = human.plan_sentence("Welcome back, Maria, this is the wick thing from yesterday.", mood="warm", rng=_rng(), now=12 * 3600)
    assert p.aside and p.level_db < -1.0 and p.speed > 1.0


def test_edge_engine_never_gets_a_stretch_factor():
    p = human.plan_sentence("First, second, third, and then the close.", mood="hype", rng=_rng(), engine_sets_rate=True, now=12 * 3600)
    assert p.speed == 1.0 and "list" in p.notes


def test_daypart_drift():
    spd_night, warm_night, _, label_n = human.daypart(now=2 * 3600)          # 02:00 UTC
    spd_open, _, pres_open, label_o = human.daypart(now=8 * 3600)             # London open
    assert label_n == "night" and spd_night < 1.0 and warm_night > 0
    assert label_o == "open" and pres_open > 0


def test_fatigue_builds_and_clears():
    c = human.TalkClock()
    assert c.fatigue(now=1000.0) == 0.0
    for i in range(60):
        c.note(55.0, now=1000.0 + i * 60)          # talking 55 s of every minute for an hour
    assert c.fatigue(now=1000.0 + 60 * 60) > 0.8
    assert c.fatigue(now=1000.0 + 60 * 60 + 7200) == 0.0


def test_time_stretch_changes_length_not_level():
    rate = 24000
    t = np.arange(rate * 2) / rate
    x = (0.3 * np.sin(2 * np.pi * 180 * t) * (1 + 0.3 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
    faster = human._wsola(x, rate, 1.08)
    slower = human._wsola(x, rate, 0.93)
    assert abs(faster.size - x.size / 1.08) < rate * 0.1
    assert abs(slower.size - x.size / 0.93) < rate * 0.1
    assert np.isfinite(faster).all() and np.isfinite(slower).all()
    assert 0.5 < np.std(faster) / np.std(x) < 1.5


def test_mouth_noises_are_quiet_and_finite():
    rate = 48000
    for fn in (human.lip_smack, human.swallow, human.inhale):
        a = fn(rate, _rng())
        assert a.size > 0 and np.isfinite(a).all()
        assert float(np.max(np.abs(a))) < 0.05


def test_render_through_humanizer_with_plan():
    rate = 48000
    voice = (0.2 * np.sin(2 * np.pi * 150 * np.arange(rate) / rate)).astype(np.float32)
    plan = human.plan_sentence("Look at this, the level held twice before.", mood="teach", rng=_rng(), now=12 * 3600)
    out = humanize_sentence(voice, rate, first=True, long_prev=False, mood="teach", seed=3, plan=plan)
    assert out.size > voice.size * 0.8 and np.isfinite(out).all() and float(np.max(np.abs(out))) <= 1.0
    murm = human.plan_sentence("Mm.", mood="calm", rng=_rng(), override={"murmur": True}, now=12 * 3600)
    assert murm.murmur and murm.level_db <= -4.0


def test_imperfections_are_rare_and_rate_limited():
    import random

    imp = Imperfections(rng=random.Random(5))
    text = "The level held twice before and that is why the buyers came back in. Price then pushed through the high with volume."
    changed = 0
    for i in range(400):
        out = imp.apply(text, "teach", now=i * 2.0)           # 800 s of talking, 2 s apart
        changed += out != text
    assert 0 < changed <= 4                                   # a couple of slips in 13 minutes, not more
    assert imp.apply("Quick reminder, this is education, not financial advice.", "teach", now=10**6) == \
        "Quick reminder, this is education, not financial advice."
    assert imp.apply("Gold is at 3,912.", "teach", now=10**6 + 1) == "Gold is at 3,912."
