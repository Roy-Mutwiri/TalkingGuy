"""Market data sources.

  crypto  -> Binance public REST (history) + WebSocket (live). No key.
  forex / stocks -> Twelve Data REST when TWELVEDATA_KEY is set (8 req/min, 800/day on the free tier),
                    otherwise yfinance (no key, delayed).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Callable

import httpx

from .store import TF_SECONDS, Candle

log = logging.getLogger("data")

CRYPTO_QUOTE = ("USDT", "USDC", "BUSD")
FOREX_PAIRS = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "XAUUSD", "XAGUSD"}


def classify(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith(CRYPTO_QUOTE):
        return "crypto"
    if s in FOREX_PAIRS:
        return "forex"
    return "stock"


def pretty_symbol(symbol: str) -> str:
    s = symbol.upper()
    if classify(s) == "crypto":
        for q in CRYPTO_QUOTE:
            if s.endswith(q):
                return f"{s[:-len(q)]}/{q[:3]}"
    if classify(s) == "forex":
        return f"{s[:3]}/{s[3:]}"
    return s


# ----------------------------------------------------------------------------- Binance
BINANCE_REST = "https://api.binance.com/api/v3"
BINANCE_WS = "wss://stream.binance.com:9443/ws"


async def binance_klines(symbol: str, tf: str, start: int, end: int, client: httpx.AsyncClient | None = None) -> list[Candle]:
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    out: list[Candle] = []
    step_ms = TF_SECONDS[tf] * 1000
    cur = start * 1000
    try:
        while cur < end * 1000:
            r = await client.get(
                f"{BINANCE_REST}/klines",
                params={"symbol": symbol.upper(), "interval": tf, "startTime": cur, "endTime": end * 1000 - 1, "limit": 1000},
            )
            r.raise_for_status()
            rows = r.json()
            if not rows:
                break
            for k in rows:
                out.append({"time": k[0] // 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])})
            cur = rows[-1][0] + step_ms
            if len(rows) < 1000:
                break
    finally:
        if own:
            await client.aclose()
    return out


async def binance_ticker_24h(symbols: list[str]) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BINANCE_REST}/ticker/24hr", params={"symbols": json.dumps([s.upper() for s in symbols], separators=(",", ":"))})
        r.raise_for_status()
        return [{"symbol": pretty_symbol(d["symbol"]).split("/")[0], "price": _fmt_price(float(d["lastPrice"])), "chg": float(d["priceChangePercent"])} for d in r.json()]


async def binance_kline_stream(symbol: str, tf: str) -> AsyncIterator[tuple[Candle, bool]]:
    """Yield (candle, closed) for every kline update. Reconnects forever."""
    import websockets

    url = f"{BINANCE_WS}/{symbol.lower()}@kline_{tf}"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, max_size=2**20) as ws:
                log.info("binance stream connected %s %s", symbol, tf)
                async for raw in ws:
                    k = json.loads(raw).get("k")
                    if not k:
                        continue
                    yield ({"time": k["t"] // 1000, "open": float(k["o"]), "high": float(k["h"]), "low": float(k["l"]), "close": float(k["c"]), "volume": float(k["v"])}, bool(k["x"]))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("binance stream error (%s), reconnecting in 3s", exc)
            await asyncio.sleep(3)


# ----------------------------------------------------------------------------- Twelve Data
TD_REST = "https://api.twelvedata.com"
TD_INTERVAL = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1day", "1w": "1week"}


class RateLimiter:
    """Simple per-minute token budget (Twelve Data free tier: 8/min)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.calls: list[float] = []

    async def wait(self) -> None:
        while True:
            now = time.monotonic()
            self.calls = [t for t in self.calls if now - t < 60]
            if len(self.calls) < self.per_minute:
                self.calls.append(now)
                return
            await asyncio.sleep(60 - (now - self.calls[0]) + 0.2)


_td_limiter = RateLimiter(7)


def td_symbol(symbol: str) -> str:
    s = symbol.upper()
    return f"{s[:3]}/{s[3:]}" if classify(s) == "forex" else s


async def twelvedata_series(symbol: str, tf: str, start: int, end: int, api_key: str) -> list[Candle]:
    out: list[Candle] = []
    async with httpx.AsyncClient(timeout=30) as client:
        cur_end = end
        while cur_end > start:
            await _td_limiter.wait()
            r = await client.get(
                f"{TD_REST}/time_series",
                params={
                    "symbol": td_symbol(symbol), "interval": TD_INTERVAL[tf], "outputsize": 5000, "timezone": "UTC", "apikey": api_key,
                    "start_date": datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "end_date": datetime.fromtimestamp(cur_end, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "order": "ASC",
                },
            )
            data = r.json()
            if data.get("status") == "error":
                raise RuntimeError(f"Twelve Data: {data.get('message')}")
            values = data.get("values", [])
            batch = []
            for v in values:
                dt = datetime.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S" if " " in v["datetime"] else "%Y-%m-%d").replace(tzinfo=timezone.utc)
                batch.append({"time": int(dt.timestamp()), "open": float(v["open"]), "high": float(v["high"]), "low": float(v["low"]), "close": float(v["close"]), "volume": float(v.get("volume") or 0)})
            out = batch + out
            if len(values) < 5000:
                break
            cur_end = batch[0]["time"] - 1
    out.sort(key=lambda c: c["time"])
    return [c for c in out if start <= c["time"] < end]


# ----------------------------------------------------------------------------- yfinance fallback
YF_TICKER = {"XAUUSD": "GC=F", "XAGUSD": "SI=F"}
YF_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d", "1w": "1wk"}


def yf_symbol(symbol: str) -> str:
    s = symbol.upper()
    if s in YF_TICKER:
        return YF_TICKER[s]
    return f"{s}=X" if classify(s) == "forex" else s


def _resample(candles: list[Candle], tf: str) -> list[Candle]:
    step = TF_SECONDS[tf]
    out: list[Candle] = []
    for c in candles:
        bucket = c["time"] - (c["time"] % step)
        if out and out[-1]["time"] == bucket:
            o = out[-1]
            o["high"] = max(o["high"], c["high"]); o["low"] = min(o["low"], c["low"]); o["close"] = c["close"]; o["volume"] += c["volume"]
        else:
            out.append({"time": bucket, "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"], "volume": c["volume"]})
    return out


def yfinance_series_sync(symbol: str, tf: str, start: int, end: int) -> list[Candle]:
    import yfinance as yf

    df = yf.download(
        yf_symbol(symbol), interval=YF_INTERVAL[tf],
        start=datetime.fromtimestamp(start, timezone.utc), end=datetime.fromtimestamp(end, timezone.utc),
        progress=False, auto_adjust=False, multi_level_index=False,
    )
    out: list[Candle] = []
    if df is None or df.empty:
        return out
    for ts, row in df.iterrows():
        t = int(ts.tz_localize("UTC").timestamp()) if ts.tzinfo is None else int(ts.timestamp())
        out.append({"time": t, "open": float(row["Open"]), "high": float(row["High"]), "low": float(row["Low"]), "close": float(row["Close"]), "volume": float(row.get("Volume", 0) or 0)})
    if tf == "4h":
        out = _resample(out, "4h")
    return [c for c in out if start <= c["time"] < end]


async def yfinance_series(symbol: str, tf: str, start: int, end: int) -> list[Candle]:
    return await asyncio.to_thread(yfinance_series_sync, symbol, tf, start, end)


# ----------------------------------------------------------------------------- routing
async def fetch_history(symbol: str, tf: str, start: int, end: int) -> list[Candle]:
    kind = classify(symbol)
    if kind == "crypto":
        return await binance_klines(symbol, tf, start, end)
    key = os.getenv("TWELVEDATA_KEY", "").strip()
    if key:
        try:
            return await twelvedata_series(symbol, tf, start, end, key)
        except Exception as exc:  # noqa: BLE001
            log.warning("Twelve Data failed for %s (%s); falling back to yfinance", symbol, exc)
    return await yfinance_series(symbol, tf, start, end)


def _fmt_price(p: float) -> str:
    if p >= 1000:
        return f"{p:,.0f}"
    if p >= 10:
        return f"{p:,.2f}"
    return f"{p:.4f}"


async def poll_latest(symbol: str, tf: str, on_candle: Callable[[Candle, bool], None], interval_s: int = 60) -> None:
    """Non-crypto live mode: re-fetch the last two candles every minute."""
    step = TF_SECONDS[tf]
    while True:
        try:
            now = int(time.time())
            candles = await fetch_history(symbol, tf, now - step * 3, now + step)
            for c in candles[-2:]:
                on_candle(c, c is not candles[-1])
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("poll %s failed: %s", symbol, exc)
        await asyncio.sleep(interval_s)
