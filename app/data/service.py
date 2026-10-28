"""DataService: one place the director and the brain ask for candles, examples and tickers.

- get_candles(): cached history (SQLite) with on-demand fetch from the right source.
- find_examples(): run a pattern scanner on recent history and return concrete windows
  the lesson planner can describe (times, prices, invalidation levels).
- ticker(): small watchlist with price and 24h change for the stage.
- live(): async generator of (candle, closed) for the market-tour segment.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import patterns, sources
from .store import TF_SECONDS, Candle, CandleStore

log = logging.getLogger("data")

DEFAULT_SYMBOLS = {
    "crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "forex": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
    "stock": ["AAPL", "NVDA", "MSFT", "SPY", "TSLA"],
}
WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M")


@dataclass
class ExampleWindow:
    symbol: str
    tf: str
    start: int            # window start (unix)
    end: int              # window end (unix, exclusive)
    hit_time: int
    label: str
    extra: dict = field(default_factory=dict)
    candles: list[Candle] = field(default_factory=list)

    def describe(self, around: int = 8) -> str:
        """Compact text the planner feeds to the model: the bars around the hit + helpful levels."""
        idx = next((i for i, c in enumerate(self.candles) if c["time"] == self.hit_time), None)
        lines = [f"symbol={self.symbol} tf={self.tf} window={iso(self.start)}..{iso(self.end)} pattern={self.label} at {iso(self.hit_time)}"]
        if self.extra:
            lines.append("details=" + ", ".join(f"{k}={_fmt(v)}" for k, v in self.extra.items()))
        if idx is not None:
            lo, hi = max(0, idx - around), min(len(self.candles), idx + around + 1)
            lines.append("bars (time open high low close):")
            for c in self.candles[lo:hi]:
                mark = "  <-- pattern" if c["time"] == self.hit_time else ""
                lines.append(f"  {iso(c['time'])} {_fmt(c['open'])} {_fmt(c['high'])} {_fmt(c['low'])} {_fmt(c['close'])}{mark}")
        highs, lows = patterns.swing_points(self.candles)
        if highs:
            lines.append("swing highs: " + ", ".join(f"{iso(h.time)}@{_fmt(h.extra['price'])}" for h in highs[-4:]))
        if lows:
            lines.append("swing lows: " + ", ".join(f"{iso(l.time)}@{_fmt(l.extra['price'])}" for l in lows[-4:]))
        lv = patterns.levels(self.candles)
        if lv:
            lines.append("levels: " + ", ".join(f"{h.label}@{_fmt(h.extra['price'])}({h.extra['touches']} touches)" for h in lv[:4]))
        wmin = min(c["low"] for c in self.candles)
        wmax = max(c["high"] for c in self.candles)
        lines.append(f"window low={_fmt(wmin)} high={_fmt(wmax)}")
        return "\n".join(lines)


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4f}" if v < 10 else f"{v:.2f}"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


class DataService:
    def __init__(self, store: CandleStore | None = None) -> None:
        self.store = store or CandleStore()
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _lock(self, symbol: str, tf: str) -> asyncio.Lock:
        return self._locks.setdefault((symbol, tf), asyncio.Lock())

    spot_reference: dict[str, float] = {}   # live spot price per symbol (set by the quote service) for basis adjustment

    async def get_candles(self, symbol: str, tf: str, start: int, end: int) -> list[Candle]:
        symbol = symbol.upper()
        step = TF_SECONDS[tf]
        start -= start % step
        end = min(end, int(time.time()) + step)
        async with self._lock(symbol, tf):
            if not self.store.is_covered(symbol, tf, start, end):
                log.info("fetching %s %s %s..%s", symbol, tf, iso(start), iso(end))
                candles = await sources.fetch_history(symbol, tf, start, end)
                self.store.upsert(symbol, tf, candles)
                if candles:
                    self.store.mark_covered(symbol, tf, start, end)
            out = self.store.get_range(symbol, tf, start, end)
        return self._spot_from_ticks(symbol, tf, start, end, out)

    def _spot_from_ticks(self, symbol: str, tf: str, start: int, end: int, fallback: list[Candle]) -> list[Candle]:
        """For gold/silver: where we hold real spot 1m candles (persisted from the live feed), resample
        them into the requested timeframe and splice them over the futures-based history."""
        if symbol not in ("XAUUSD", "XAGUSD") or tf == "1m" or os.getenv("TWELVEDATA_KEY", "").strip():
            return self._to_spot(symbol, fallback) if tf != "1m" else fallback
        step = TF_SECONDS[tf]
        ticks = self.store.get_range(symbol, "1m", start, end)
        base = self._to_spot(symbol, fallback)
        if len(ticks) < 30:
            return base
        bars: dict[int, Candle] = {}
        counts: dict[int, int] = {}
        for c in ticks:
            b = c["time"] - c["time"] % step
            counts[b] = counts.get(b, 0) + 1
            if b in bars:
                o = bars[b]; o["high"] = max(o["high"], c["high"]); o["low"] = min(o["low"], c["low"]); o["close"] = c["close"]
            else:
                bars[b] = {"time": b, "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"], "volume": 0.0}
        need = max(1, int(step / 60 * 0.6))      # a bar must be at least 60% covered by live minutes to replace history
        good = {b: v for b, v in bars.items() if counts[b] >= need or b == max(bars)}
        merged = {c["time"]: c for c in base}
        merged.update(good)
        return [merged[k] for k in sorted(merged)]

    def _to_spot(self, symbol: str, candles: list[Candle]) -> list[Candle]:
        """Gold/silver history without a key comes from the futures contract (GC=F), which trades above spot.
        Shift the whole series by the current basis so charts line up with the live spot tables."""
        if symbol not in ("XAUUSD", "XAGUSD") or not candles or os.getenv("TWELVEDATA_KEY", "").strip():
            return candles
        ref = self.spot_reference.get(symbol)
        if not ref:
            return candles
        basis = self._gold_basis(symbol, ref, candles[-1])
        if basis is None or abs(basis) < 0.01 or abs(basis) > ref * 0.03:
            return candles
        return [{**c, "open": c["open"] + basis, "high": c["high"] + basis, "low": c["low"] + basis, "close": c["close"] + basis} for c in candles]

    def _gold_basis(self, symbol: str, ref: float, last: Candle) -> float | None:
        """spot minus futures, measured on the freshest futures close we hold (5m/15m/1h series from
        Yahoo; the 1m series is live spot and must not be used). Cached on disk so older windows
        loaded while no fresh futures candle exists still get the last known basis."""
        import json
        from pathlib import Path

        cache = Path("data_cache/gold_basis.json")
        now = time.time()
        fresh: list[tuple[float, float]] = []
        for tf in ("5m", "15m", "1h"):
            lst = self.store.last(symbol, tf, 1)
            if lst and now - lst[-1]["time"] < 2 * TF_SECONDS[tf] + 120:
                fresh.append((now - lst[-1]["time"], lst[-1]["close"]))
        if now - last["time"] < 20 * 60:
            fresh.append((now - last["time"], last["close"]))
        if fresh:
            fresh.sort()
            basis = ref - fresh[0][1]
            try:
                cache.parent.mkdir(exist_ok=True)
                cache.write_text(json.dumps({"symbol": symbol, "basis": basis, "ts": now}))
            except Exception:  # noqa: BLE001
                pass
            return basis
        try:
            c = json.loads(cache.read_text())
            if c.get("symbol") == symbol and now - c.get("ts", 0) < 7 * 86400:
                return float(c["basis"])
        except Exception:  # noqa: BLE001
            pass
        return None

    async def recent(self, symbol: str, tf: str, bars: int) -> list[Candle]:
        now = int(time.time())
        return await self.get_candles(symbol, tf, now - TF_SECONDS[tf] * bars, now)

    LIVE_WINDOW = 90   # bars shown on the live chart during a lesson

    async def find_examples(self, scanner: str, symbols: list[str], tf: str, lookback_bars: int = 600,
                            before: int = 45, after: int = 25, max_examples: int = 3) -> list[ExampleWindow]:
        """LIVE ONLY: the window is always the last LIVE_WINDOW real bars ending now. The example
        pattern must occur inside that window (not in the final 3 bars, so some outcome is visible).
        If the requested timeframe has no instance, higher timeframes are tried so the chart stays live."""
        out: list[ExampleWindow] = []
        tfs = [tf] + [t for t in ("15m", "1h", "4h", "1d") if t != tf]
        for symbol in symbols:
            for t in tfs:
                step = TF_SECONDS[t]
                try:
                    candles = await self.recent(symbol, t, self.LIVE_WINDOW + 10)
                except Exception as exc:  # noqa: BLE001
                    log.warning("no data for %s %s: %s", symbol, t, exc)
                    continue
                if len(candles) < 30:
                    continue
                win = candles[-self.LIVE_WINDOW:]
                hits = patterns.scan(scanner, win) if scanner != "none" else []
                hits = [h for h in hits if 8 <= h.index < len(win) - 3]
                if not hits:
                    continue
                h = max(hits, key=lambda x: x.index)      # the most recent instance on the live chart
                out.append(ExampleWindow(symbol, t, win[0]["time"], win[-1]["time"] + step, h.time, h.label, dict(h.extra), win))
                break
            if len(out) >= max_examples:
                break
        return out[:max_examples]

    async def plain_window(self, symbol: str, tf: str, bars: int = 90) -> ExampleWindow:
        """A recent window with no particular pattern (for concept-only lessons)."""
        candles = await self.recent(symbol, tf, bars)
        if not candles:
            raise RuntimeError(f"no candles for {symbol} {tf}")
        return ExampleWindow(symbol, tf, candles[0]["time"], candles[-1]["time"] + TF_SECONDS[tf], candles[-1]["time"], "recent price action", {}, candles)

    async def ticker(self, symbols: list[str] | None = None) -> list[dict]:
        symbols = symbols or WATCHLIST
        crypto = [s for s in symbols if sources.classify(s) == "crypto"]
        items: list[dict] = []
        if crypto:
            try:
                items += await sources.binance_ticker_24h(crypto)
            except Exception as exc:  # noqa: BLE001
                log.warning("ticker failed: %s", exc)
        for s in symbols:
            if sources.classify(s) == "crypto":
                continue
            try:
                d = await self.recent(s, "1d", 3)
                if len(d) >= 2:
                    chg = (d[-1]["close"] / d[-2]["close"] - 1) * 100
                    items.append({"symbol": sources.pretty_symbol(s), "price": sources._fmt_price(d[-1]["close"]), "chg": chg})
            except Exception as exc:  # noqa: BLE001
                log.warning("ticker %s failed: %s", s, exc)
        return items

    async def live(self, symbol: str, tf: str):
        """Yield (candle, closed) updates. Crypto streams from Binance; others poll once a minute."""
        if sources.classify(symbol) == "crypto":
            async for item in sources.binance_kline_stream(symbol, tf):
                yield item
        else:
            q: asyncio.Queue = asyncio.Queue()
            task = asyncio.create_task(sources.poll_latest(symbol, tf, lambda c, closed: q.put_nowait((c, closed))))
            try:
                while True:
                    yield await q.get()
            finally:
                task.cancel()
