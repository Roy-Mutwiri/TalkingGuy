"""Make text sound human when read by a TTS voice: tickers, jargon, timeframes, numbers.

humanize("BTCUSDT on the 4h, RSI at 71, price 79961, EURUSD 1.0850")
 -> "Bitcoin on the four hour, R S I at 71, price 79,961, euro dollar 1.0850"
"""
from __future__ import annotations

import re

_TICKERS = {
    "BTCUSDT": "Bitcoin", "BTC/USDT": "Bitcoin", "BTC/USD": "Bitcoin", "BTCUSD": "Bitcoin", "BTC": "Bitcoin",
    "ETHUSDT": "Ethereum", "ETH/USDT": "Ethereum", "ETH/USD": "Ethereum", "ETH": "Ethereum",
    "SOLUSDT": "Solana", "SOL/USDT": "Solana", "SOL/USD": "Solana", "SOL": "Solana",
    "XAUUSD": "gold", "XAU/USD": "gold", "XAU": "gold", "XAGUSD": "silver", "XAG/USD": "silver",
    "EURUSD": "euro dollar", "EUR/USD": "euro dollar", "GBPUSD": "pound dollar", "GBP/USD": "pound dollar",
    "USDJPY": "dollar yen", "USD/JPY": "dollar yen", "AUDUSD": "aussie dollar", "AUD/USD": "aussie dollar",
    "USDCAD": "dollar cad", "USD/CAD": "dollar cad", "USDCHF": "dollar swiss", "USD/CHF": "dollar swiss",
    "NAS100": "the Nasdaq", "US30": "the Dow", "SPX500": "the S and P", "SPY": "the S and P ETF, SPY",
    "AAPL": "Apple", "NVDA": "Nvidia", "MSFT": "Microsoft", "TSLA": "Tesla",
}
_JARGON = {
    "RSI": "R S I", "MACD": "mac D", "EMA": "E M A", "SMA": "S M A", "VWAP": "vee wap", "ATR": "A T R",
    "POC": "point of control", "VAH": "value area high", "VAL": "value area low", "HTF": "higher timeframe",
    "LTF": "lower timeframe", "OHLC": "open high low close", "FOMO": "fomo", "S/R": "support and resistance",
    "SL": "stop loss", "TP": "take profit", "R:R": "risk to reward", "RR": "risk to reward", "BOS": "break of structure",
    "CHoCH": "change of character", "OB": "order block", "FVG": "fair value gap", "PA": "price action", "TA": "technical analysis",
    "ICT": "I C T", "SMC": "smart money concepts", "UTC": "U T C", "ETF": "E T F", "CPI": "C P I", "FOMC": "the Fed meeting",
    "NFP": "non farm payrolls", "GMT": "G M T", "EST": "eastern time", "AI": "A I", "Q&A": "Q and A", "DCA": "dollar cost averaging",
}
_TF = {"1m": "one minute", "5m": "five minute", "15m": "fifteen minute", "30m": "thirty minute",
       "1h": "one hour", "4h": "four hour", "1d": "daily", "1w": "weekly", "1D": "daily", "1W": "weekly", "4H": "four hour", "1H": "one hour"}

_ticker_rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _TICKERS), key=len, reverse=True)) + r")\b")
_jargon_rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _JARGON), key=len, reverse=True)) + r")\b")
_tf_rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _TF), key=len, reverse=True)) + r")\b(?=\s*(chart|timeframe|candle|candles|bar|bars|close|closes|,|\.|$))")
_bigint_rx = re.compile(r"(?<![\d.,])(\d{4,6})(?!\d|\.\d|,\d|%)")
_k_rx = re.compile(r"\b(\d+(?:\.\d+)?)[kK]\b")
_pct_rx = re.compile(r"(\d)\s*%")
_x_rx = re.compile(r"\b(\d+(?:\.\d+)?)x\b")


def _ascii_fold(text: str) -> str:
    import unicodedata
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return folded.encode("ascii", "ignore").decode("ascii")


def humanize(text: str) -> str:
    from ..chat.names import strip_for_speech
    from .tags import protect, restore

    text, tags = protect(text)                # [laughs] [sighs] ... are kept for an expressive voice engine
    t = strip_for_speech(text)                # never read emojis or decorative symbols aloud
    t = _ascii_fold(t)                        # accents/foreign letters -> plain ASCII, so a multilingual voice never switches language
    t = re.sub(r"[#*_~`^|<>\[\]{}\\]", " ", t)  # markdown/decoration characters are silent too
    t = re.sub(r"\s+@(\w+)", r" \1", t)       # "@maria" -> "maria"
    t = _ticker_rx.sub(lambda m: _TICKERS[m.group(1)], t)
    t = _tf_rx.sub(lambda m: _TF[m.group(1)], t)
    t = _jargon_rx.sub(lambda m: _JARGON[m.group(1)], t)
    t = _k_rx.sub(lambda m: f"{m.group(1)} thousand", t)
    t = _bigint_rx.sub(lambda m: f"{int(m.group(1)):,}", t)   # 79961 -> 79,961 (read as a number, not digits)
    t = _pct_rx.sub(r"\1 percent", t)
    t = _x_rx.sub(r"\1 times", t)
    t = re.sub(r"\s+-\s+", ", ", t)          # " - " dashes become a breath
    t = re.sub(r"\s*—\s*", ", ", t)
    t = re.sub(r"\s*\(([^)]{1,40})\)\s*", r", \1, ", t)  # (parentheses) read as asides
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return restore(t, tags)
