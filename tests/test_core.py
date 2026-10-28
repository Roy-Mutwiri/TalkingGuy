import json
from pathlib import Path

import pytest

from app.brain import filters
from app.brain.client import clean_schema
from app.brain.curriculum import Curriculum
from app.brain.schema import LessonScript, ChatReply, iso_to_unix
from app.data import patterns

ROOT = Path(__file__).resolve().parents[1]


def test_sample_lesson_validates():
    script = LessonScript.model_validate_json((ROOT / "tests/fixtures/sample_lesson.json").read_text(encoding="utf-8"))
    assert script.beats[0].chart[0].action == "load"
    assert iso_to_unix("2025-09-01") == 1756684800


def test_schema_cleaning_strips_unsupported_keywords():
    s = json.dumps(clean_schema(LessonScript))
    for bad in ("maxLength", "minLength", "minimum", "maximum", "minItems", "maxItems"):
        assert bad not in s
    assert '"additionalProperties": false' in s
    assert "ChatReply" in json.dumps(clean_schema(ChatReply)) or "say" in json.dumps(clean_schema(ChatReply))


@pytest.mark.parametrize("text", [
    "Buy now before it pumps.",
    "My price target is 120k by December.",
    "Bitcoin will hit 150,000 soon.",
    "This setup is guaranteed to work.",
    "I made $500 a day with this.",
    "DM me for signals.",
    "You should buy this dip.",
])
def test_filter_catches_violations(text):
    assert filters.violations(text), text


@pytest.mark.parametrize("text", [
    "Price came back to support and buyers stepped in.",
    "The low of the engulfing candle is where the idea would be wrong.",
    "Nobody knows where price goes next, so we work with levels.",
    "Risk management means deciding what you lose before you enter anything.",
])
def test_filter_allows_education(text):
    assert not filters.violations(text), text


def test_sanitize_drops_only_bad_sentences():
    clean, bad = filters.sanitize("Support held here. Buy now before it pumps. The invalidation is the low.")
    assert "Buy now" not in clean and "Support held" in clean and "invalidation" in clean
    assert len(bad) == 1


def _candles():
    # down move then a bullish engulfing, then up move
    base = 100.0
    out = []
    t = 1_700_000_000
    prices = [base - i * 0.8 for i in range(8)]
    for i, p in enumerate(prices):
        out.append({"time": t + i * 3600, "open": p, "high": p + 0.3, "low": p - 1.0, "close": p - 0.7, "volume": 100})
    last = out[-1]
    out.append({"time": last["time"] + 3600, "open": last["close"] - 0.1, "high": last["open"] + 1.5, "low": last["close"] - 0.3, "close": last["open"] + 1.2, "volume": 400})
    for i in range(1, 8):
        p = out[-1]["close"]
        out.append({"time": out[-1]["time"] + 3600, "open": p, "high": p + 1.2, "low": p - 0.2, "close": p + 0.9, "volume": 120})
    return out


def test_engulfing_scanner_finds_the_engulfing_bar():
    c = _candles()
    hits = patterns.engulfing(c, bullish=True)
    assert hits and hits[0].index == 8
    assert hits[0].extra["invalidation"] == c[8]["low"]


def test_volume_spike_and_rsi_do_not_crash():
    c = _candles() * 3
    for i, x in enumerate(c):
        x["time"] = 1_700_000_000 + i * 3600
    assert isinstance(patterns.volume_spikes(c, n=5), list)
    assert isinstance(patterns.rsi_extremes(c, True, n=5), list)
    assert all(name in patterns.SCANNERS for name in ("engulfing_bull", "support_level", "breakout_up", "range"))


def test_curriculum_loads():
    cur = Curriculum()
    assert len(cur.modules) >= 8, "curriculum files missing"
    assert len(cur.lessons) >= 40
    for l in cur.lessons:
        assert l.scanner in patterns.SCANNERS or l.scanner == "none", f"{l.key} has unknown scanner {l.scanner}"
        assert l.tf in ("15m", "1h", "4h", "1d"), l.key
    assert cur.find("bullish engulfing candle") is not None
