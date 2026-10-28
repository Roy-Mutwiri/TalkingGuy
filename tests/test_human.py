from datetime import datetime, timezone
from pathlib import Path

from app.brain.memory import LocalMemory
from app.brain.phrases import BANKS, Picker
from app.data.market_hours import gold_market_open, primary_symbol, session_name
from app.voice.pronounce import humanize


def test_humanize_tickers_jargon_numbers():
    out = humanize("BTCUSDT on the 4h chart, RSI at 71, price 79961, EURUSD 1.0850, XAUUSD moved 2% to 2.5k")
    assert "Bitcoin" in out and "four hour chart" in out and "R S I" in out
    assert "79,961" in out and "1.0850" in out and "euro dollar" in out and "gold" in out
    assert "2 percent" in out and "2.5 thousand" in out


def test_humanize_leaves_normal_text():
    s = "Price came back to support and buyers stepped in."
    assert humanize(s) == s


def test_gold_hours():
    utc = timezone.utc
    assert not gold_market_open(datetime(2026, 10, 24, 12, tzinfo=utc))      # Saturday
    assert not gold_market_open(datetime(2026, 10, 25, 12, tzinfo=utc))      # Sunday noon
    assert gold_market_open(datetime(2026, 10, 25, 23, 30, tzinfo=utc))      # Sunday night open
    assert gold_market_open(datetime(2026, 10, 27, 14, tzinfo=utc))          # Tuesday
    assert not gold_market_open(datetime(2026, 10, 27, 22, 30, tzinfo=utc))  # daily break
    assert not gold_market_open(datetime(2026, 10, 30, 22, 5, tzinfo=utc))   # Friday close
    assert primary_symbol(datetime(2026, 10, 24, 12, tzinfo=utc)) == "BTCUSDT"
    assert primary_symbol(datetime(2026, 10, 27, 14, tzinfo=utc)) == "XAUUSD"
    assert session_name(datetime(2026, 10, 27, 9, tzinfo=utc)) == "the London session"


def test_picker_never_repeats_back_to_back(tmp_path: Path):
    p = Picker(path=tmp_path / "h.json", memory=5)
    picks = [p.pick("bridge") for _ in range(40)]
    for i in range(1, len(picks)):
        assert picks[i] != picks[i - 1]
    # persisted history survives a restart
    p2 = Picker(path=tmp_path / "h.json", memory=5)
    assert p2.history["bridge"] == p.history["bridge"]
    for bank in BANKS:
        assert len(BANKS[bank]) >= 2, bank


def test_picker_formats():
    p = Picker(path=Path("data_cache/test_phrases.json"))
    s = p.pick("lesson_open", topic="wicks", market="gold", tf="one hour")
    assert "wicks" in s and "gold" in s


def test_local_memory_search(tmp_path: Path):
    m = LocalMemory(tmp_path / "m.db")
    m.add("Viewer maria asked about long wicks at support", "qa", viewer="maria")
    m.add("Taught lesson The bullish engulfing candle on gold", "lesson")
    assert m.search("wicks", viewer="maria")
    assert m.search("engulfing", kind="lesson")
    assert not m.search("engulfing", viewer="maria")
    assert m.recent("lesson", 5)[0].startswith("Taught lesson")
