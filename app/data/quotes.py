"""Real-time quotes for the room screens.

Sources, best first:
  crypto (BTC, ETH, SOL, PAXG)  Binance WebSocket, tick-level, no key.
  gold / forex (XAU/USD ...)    Twelve Data WebSocket when TWELVEDATA_KEY is set (real-time);
                                otherwise Yahoo Finance polled every 15 s (delayed ~15 min, labelled so).

Each update is a dict {"symbol": "XAU/USD", "price": float, "chg": float (24h %), "ts": unix, "delayed": bool}
and 1-minute candles {"symbol": ..., "candle": {...}} for the mini charts. A QuoteService fans them out
to any number of async subscribers (the director forwards them to the stage over the hub).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import httpx

from .sources import pretty_symbol

log = logging.getLogger("quotes")

CRYPTO_STREAMS = ["btcusdt", "ethusdt", "solusdt", "paxgusdt"]
FX_SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY"]
YF = {"XAU/USD": "GC=F", "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X"}
SWISSQUOTE = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/{base}/{quote}"


class QuoteService:
    def __init__(self, data=None) -> None:
        self.data = data                     # DataService, for the spot reference and 1m persistence
        self._persist_t: dict[str, int] = {}
        self.latest: dict[str, dict] = {}
        self.candles: dict[str, list[dict]] = {}
        self.subscribers: list[asyncio.Queue] = []
        self._day_open: dict[str, float] = {}

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.subscribers.append(q)
        return q

    def _publish(self, msg: dict) -> None:
        for q in list(self.subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(msg)

    def _quote(self, symbol: str, price: float, chg: float | None, delayed: bool) -> None:
        if chg is None:
            base = self._day_open.get(symbol)
            chg = (price / base - 1) * 100 if base else 0.0
        self.latest[symbol] = {"type": "quote", "symbol": symbol, "price": price, "chg": round(chg, 2), "ts": time.time(), "delayed": delayed}
        self._publish(self.latest[symbol])
        if self.data is not None and not delayed and symbol in ("XAU/USD", "XAG/USD"):
            self.data.spot_reference[symbol.replace("/", "")] = price

    def _candle(self, symbol: str, c: dict) -> None:
        arr = self.candles.setdefault(symbol, [])
        if arr and arr[-1]["time"] == c["time"]:
            arr[-1] = c
        else:
            arr.append(c)
            del arr[:-240]
        self._publish({"type": "kline", "symbol": symbol, "candle": c})

    # ------------------------------------------------------------------ Binance
    async def _binance(self) -> None:
        import websockets

        streams = "/".join(f"{s}@kline_1m" for s in CRYPTO_STREAMS) + "/" + "/".join(f"{s}@miniTicker" for s in CRYPTO_STREAMS)
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, max_size=2**20) as ws:
                    log.info("binance quotes connected")
                    async for raw in ws:
                        d = json.loads(raw).get("data") or {}
                        et = d.get("e")
                        if et == "24hrMiniTicker":
                            sym = pretty_symbol(d["s"])
                            price, open_ = float(d["c"]), float(d["o"])
                            self._quote(sym, price, (price / open_ - 1) * 100 if open_ else 0.0, False)
                        elif et == "kline":
                            k = d["k"]
                            self._candle(pretty_symbol(d["s"]), {"time": k["t"] // 1000, "open": float(k["o"]), "high": float(k["h"]),
                                                                 "low": float(k["l"]), "close": float(k["c"]), "volume": float(k["v"])})
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("binance quotes error (%s); reconnecting", exc)
                await asyncio.sleep(3)

    # ------------------------------------------------------------------ Twelve Data (real-time gold/forex)
    async def _twelvedata_ws(self, key: str) -> None:
        import websockets

        url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={key}"
        while True:
            try:
                async with websockets.connect(url, ping_interval=10) as ws:
                    await ws.send(json.dumps({"action": "subscribe", "params": {"symbols": ",".join(FX_SYMBOLS)}}))
                    log.info("twelvedata quotes connected")
                    hb = asyncio.get_running_loop().time()
                    async for raw in ws:
                        d = json.loads(raw)
                        if d.get("event") == "price":
                            sym = d["symbol"]
                            price = float(d["price"])
                            self._quote(sym, price, None, False)
                            self._tick_to_candle(sym, price, int(d.get("timestamp", time.time())))
                        if asyncio.get_running_loop().time() - hb > 10:
                            await ws.send(json.dumps({"action": "heartbeat"}))
                            hb = asyncio.get_running_loop().time()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("twelvedata ws error (%s); reconnecting in 10s", exc)
                await asyncio.sleep(10)

    def _tick_to_candle(self, symbol: str, price: float, ts: int) -> None:
        minute = ts - ts % 60
        arr = self.candles.setdefault(symbol, [])
        if arr and arr[-1]["time"] == minute:
            c = arr[-1]
            c["high"] = max(c["high"], price); c["low"] = min(c["low"], price); c["close"] = price
        else:
            # a new minute started: persist the completed spot candle so real spot history accumulates
            if arr and self.data is not None:
                done = arr[-1]
                try:
                    self.data.store.upsert(symbol.replace("/", ""), "1m", [done])
                except Exception as exc:  # noqa: BLE001
                    log.debug("persist 1m %s: %s", symbol, exc)
            c = {"time": minute, "open": price, "high": price, "low": price, "close": price, "volume": 0.0}
        self._candle(symbol, c)

    # ------------------------------------------------------------------ Swissquote (real-time bank quotes, no key)
    async def _swissquote_poll(self, interval_s: float = 2.0) -> None:
        """Live spot for gold/forex from Swissquote's public best-bid/offer feed, every 2 s."""
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "Mozilla/5.0"}) as client:
            fails = 0
            while True:
                for sym in FX_SYMBOLS:
                    if sym == "XAU/USD" and os.getenv("GOLD_SOURCE", "swissquote").lower() == "goldapi":
                        continue
                    base, quote = sym.split("/")
                    try:
                        r = await client.get(SWISSQUOTE.format(base=base, quote=quote))
                        if r.status_code != 200:
                            fails += 1
                            continue
                        rows = r.json()
                        # pick the tightest spread profile across venues
                        best = None
                        for venue in rows:
                            for prof in venue.get("spreadProfilePrices", []):
                                bid, ask = float(prof["bid"]), float(prof["ask"])
                                if best is None or (ask - bid) < (best[1] - best[0]):
                                    best = (bid, ask, int(venue.get("ts", time.time() * 1000)) // 1000)
                        if best is None:
                            continue
                        bid, ask, ts = best
                        mid = (bid + ask) / 2
                        self._day_open.setdefault(sym, mid)
                        self._quote(sym, mid, None, False)
                        self._tick_to_candle(sym, mid, ts or int(time.time()))
                        fails = 0
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        fails += 1
                        if fails in (3, 50, 500):
                            log.warning("swissquote %s: %s", sym, exc)
                await asyncio.sleep(interval_s)

    # ------------------------------------------------------------------ gold-api.com (alternative spot gold)
    async def _goldapi_poll(self, interval_s: float = 3.0) -> None:
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "Mozilla/5.0"}) as client:
            while True:
                try:
                    r = await client.get("https://api.gold-api.com/price/XAU")
                    if r.status_code == 200:
                        price = float(r.json()["price"])
                        self._quote("XAU/USD", price, None, False)
                        self._tick_to_candle("XAU/USD", price, int(time.time()))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    log.debug("gold-api: %s", exc)
                await asyncio.sleep(interval_s)

    # ------------------------------------------------------------------ Yahoo (history seed + daily change)
    async def _yahoo_poll(self, interval_s: int = 15, once: bool = False) -> None:
        first = True
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
            while True:
                for sym, yf in YF.items():
                    try:
                        r = await client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{yf}", params={"interval": "1m", "range": "1d"})
                        if r.status_code != 200:
                            continue
                        res = r.json()["chart"]["result"][0]
                        meta = res["meta"]
                        price = float(meta.get("regularMarketPrice") or 0)
                        prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0)
                        if prev:
                            self._day_open[sym] = prev   # daily % change reference for the live ticks
                        if price and not once:
                            self._quote(sym, price, (price / prev - 1) * 100 if prev else None, True)
                        ts = res.get("timestamp") or []
                        q = res["indicators"]["quote"][0]
                        if first:
                            arr = [{"time": int(ts[i]), "open": float(q["open"][i]), "high": float(q["high"][i]), "low": float(q["low"][i]),
                                    "close": float(q["close"][i]), "volume": float(q["volume"][i] or 0)} for i in range(len(ts))
                                   if None not in (q["open"][i], q["high"][i], q["low"][i], q["close"][i])]
                            self.candles[sym] = arr[-240:]
                            self._publish({"type": "kline", "symbol": sym, "candles": arr[-150:]})
                        for i in range(max(0, len(ts) - 3), len(ts)):
                            if None in (q["open"][i], q["high"][i], q["low"][i], q["close"][i]):
                                continue
                            self._candle(sym, {"time": int(ts[i]), "open": float(q["open"][i]), "high": float(q["high"][i]),
                                               "low": float(q["low"][i]), "close": float(q["close"][i]), "volume": float(q["volume"][i] or 0)})
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        log.debug("yahoo %s: %s", sym, exc)
                first = False
                if once:
                    return
                await asyncio.sleep(interval_s)

    # ------------------------------------------------------------------ backfill
    async def _backfill_binance(self) -> None:
        """Seed the mini charts with the last two hours of 1-minute candles."""
        async with httpx.AsyncClient(timeout=15) as client:
            for s in CRYPTO_STREAMS:
                try:
                    r = await client.get("https://api.binance.com/api/v3/klines", params={"symbol": s.upper(), "interval": "1m", "limit": 150})
                    r.raise_for_status()
                    sym = pretty_symbol(s.upper())
                    arr = [{"time": k[0] // 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])} for k in r.json()]
                    self.candles[sym] = arr
                    self._publish({"type": "kline", "symbol": sym, "candles": arr})
                except Exception as exc:  # noqa: BLE001
                    log.debug("backfill %s: %s", s, exc)

    # ------------------------------------------------------------------ run
    async def run(self) -> None:
        await self._backfill_binance()
        tasks = [asyncio.create_task(self._binance())]
        await self._yahoo_poll(once=True)            # one pass: 1-minute history + day-open reference
        key = os.getenv("TWELVEDATA_KEY", "").strip()
        if key:
            tasks.append(asyncio.create_task(self._twelvedata_ws(key)))
        else:
            tasks.append(asyncio.create_task(self._swissquote_poll()))   # real-time spot, no key
            if os.getenv("GOLD_SOURCE", "swissquote").lower() == "goldapi":
                tasks.append(asyncio.create_task(self._goldapi_poll()))
        log.info("gold/forex live source: %s (gold: %s)", "twelvedata" if key else "swissquote", os.getenv("GOLD_SOURCE", "swissquote"))
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
