"""Small, dependable pattern scanners over candle lists. Each returns a list of
`Hit(index, time, label, extra)` so the planner can pick genuine chart examples.

The scanners are deliberately simple and textbook so what the teacher says on air
matches what is visibly on the chart.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .store import Candle


@dataclass
class Hit:
    index: int
    time: int
    label: str
    extra: dict = field(default_factory=dict)


def _body(c: Candle) -> float:
    return abs(c["close"] - c["open"])


def _range(c: Candle) -> float:
    return max(1e-12, c["high"] - c["low"])


def _avg_range(candles: list[Candle], i: int, n: int = 14) -> float:
    lo = max(0, i - n)
    seg = candles[lo:i] or candles[: i + 1]
    return sum(_range(c) for c in seg) / len(seg)


# --------------------------------------------------------------------------- candlestick patterns
def engulfing(candles: list[Candle], bullish: bool = True, min_prior_move: int = 3) -> list[Hit]:
    out = []
    for i in range(min_prior_move + 1, len(candles)):
        p, c = candles[i - 1], candles[i]
        if bullish:
            prior_down = all(candles[j]["close"] < candles[j]["open"] for j in range(i - min_prior_move, i)) or candles[i - 1]["close"] < candles[i - min_prior_move]["open"]
            if p["close"] < p["open"] and c["close"] > c["open"] and c["close"] > p["open"] and c["open"] <= p["close"] and _body(c) > _body(p) * 1.1 and prior_down:
                out.append(Hit(i, c["time"], "bullish engulfing", {"invalidation": c["low"]}))
        else:
            prior_up = all(candles[j]["close"] > candles[j]["open"] for j in range(i - min_prior_move, i)) or candles[i - 1]["close"] > candles[i - min_prior_move]["open"]
            if p["close"] > p["open"] and c["close"] < c["open"] and c["close"] < p["open"] and c["open"] >= p["close"] and _body(c) > _body(p) * 1.1 and prior_up:
                out.append(Hit(i, c["time"], "bearish engulfing", {"invalidation": c["high"]}))
    return out


def pin_bar(candles: list[Candle], bullish: bool = True) -> list[Hit]:
    out = []
    for i, c in enumerate(candles):
        rng = _range(c)
        body = _body(c)
        upper = c["high"] - max(c["open"], c["close"])
        lower = min(c["open"], c["close"]) - c["low"]
        if body > rng * 0.35:
            continue
        if bullish and lower >= rng * 0.6 and upper <= rng * 0.2:
            out.append(Hit(i, c["time"], "bullish pin bar", {"invalidation": c["low"]}))
        elif not bullish and upper >= rng * 0.6 and lower <= rng * 0.2:
            out.append(Hit(i, c["time"], "bearish pin bar", {"invalidation": c["high"]}))
    return out


def doji(candles: list[Candle]) -> list[Hit]:
    return [Hit(i, c["time"], "doji") for i, c in enumerate(candles) if _body(c) <= _range(c) * 0.1 and _range(c) > _avg_range(candles, i) * 0.6]


def inside_bar(candles: list[Candle]) -> list[Hit]:
    out = []
    for i in range(1, len(candles)):
        p, c = candles[i - 1], candles[i]
        if c["high"] < p["high"] and c["low"] > p["low"]:
            out.append(Hit(i, c["time"], "inside bar", {"mother_high": p["high"], "mother_low": p["low"]}))
    return out


# --------------------------------------------------------------------------- structure
def swing_points(candles: list[Candle], lookback: int = 3) -> tuple[list[Hit], list[Hit]]:
    highs, lows = [], []
    for i in range(lookback, len(candles) - lookback):
        c = candles[i]
        win = candles[i - lookback: i + lookback + 1]
        if c["high"] == max(w["high"] for w in win):
            highs.append(Hit(i, c["time"], "swing high", {"price": c["high"]}))
        if c["low"] == min(w["low"] for w in win):
            lows.append(Hit(i, c["time"], "swing low", {"price": c["low"]}))
    return highs, lows


def higher_highs_lows(candles: list[Candle], lookback: int = 3, n: int = 3) -> list[Hit]:
    """Return the last swing high of each run of >= n higher highs and higher lows."""
    highs, lows = swing_points(candles, lookback)
    out = []
    for k in range(n - 1, min(len(highs), len(lows))):
        hs, ls = highs[k - n + 1: k + 1], lows[k - n + 1: k + 1]
        if all(hs[j].extra["price"] > hs[j - 1].extra["price"] for j in range(1, n)) and all(ls[j].extra["price"] > ls[j - 1].extra["price"] for j in range(1, n)):
            out.append(Hit(hs[-1].index, hs[-1].time, "uptrend structure", {"highs": [h.extra["price"] for h in hs], "lows": [l.extra["price"] for l in ls]}))
    return out


def lower_highs_lows(candles: list[Candle], lookback: int = 3, n: int = 3) -> list[Hit]:
    highs, lows = swing_points(candles, lookback)
    out = []
    for k in range(n - 1, min(len(highs), len(lows))):
        hs, ls = highs[k - n + 1: k + 1], lows[k - n + 1: k + 1]
        if all(hs[j].extra["price"] < hs[j - 1].extra["price"] for j in range(1, n)) and all(ls[j].extra["price"] < ls[j - 1].extra["price"] for j in range(1, n)):
            out.append(Hit(ls[-1].index, ls[-1].time, "downtrend structure", {"highs": [h.extra["price"] for h in hs], "lows": [l.extra["price"] for l in ls]}))
    return out


def levels(candles: list[Candle], lookback: int = 3, tolerance: float = 0.004, min_touches: int = 2) -> list[Hit]:
    """Cluster swing highs/lows into horizontal levels touched >= min_touches times."""
    highs, lows = swing_points(candles, lookback)
    pts = [(h.extra["price"], h) for h in highs] + [(l.extra["price"], l) for l in lows]
    pts.sort(key=lambda x: x[0])
    out: list[Hit] = []
    i = 0
    while i < len(pts):
        base = pts[i][0]
        group = [pts[i]]
        j = i + 1
        while j < len(pts) and abs(pts[j][0] - base) / base <= tolerance:
            group.append(pts[j]); j += 1
        if len(group) >= min_touches:
            price = sum(p for p, _ in group) / len(group)
            last = max(group, key=lambda g: g[1].index)[1]
            kind = "support" if last.label == "swing low" else "resistance"
            out.append(Hit(last.index, last.time, f"{kind} level", {"price": price, "touches": len(group)}))
        i = j
    return out


def breakouts(candles: list[Candle], lookback: int = 20, up: bool = True) -> list[Hit]:
    out = []
    for i in range(lookback, len(candles)):
        prior = candles[i - lookback: i]
        c = candles[i]
        if up and c["close"] > max(p["high"] for p in prior) and _body(c) > _avg_range(candles, i) * 0.8:
            out.append(Hit(i, c["time"], "breakout up", {"level": max(p["high"] for p in prior)}))
        if not up and c["close"] < min(p["low"] for p in prior) and _body(c) > _avg_range(candles, i) * 0.8:
            out.append(Hit(i, c["time"], "breakout down", {"level": min(p["low"] for p in prior)}))
    return out


def ranges(candles: list[Candle], window: int = 30, max_width: float = 0.05) -> list[Hit]:
    out = []
    i = window
    while i <= len(candles):
        seg = candles[i - window: i]
        hi, lo = max(c["high"] for c in seg), min(c["low"] for c in seg)
        if (hi - lo) / lo <= max_width:
            out.append(Hit(i - 1, seg[-1]["time"], "range", {"high": hi, "low": lo, "start": seg[0]["time"]}))
            i += window
        else:
            i += 5
    return out


# --------------------------------------------------------------------------- indicators
def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def rsi(values: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= n:
        return out
    gains = [max(0.0, values[i] - values[i - 1]) for i in range(1, len(values))]
    losses = [max(0.0, values[i - 1] - values[i]) for i in range(1, len(values))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(values)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def sma_cross(candles: list[Candle], fast: int = 20, slow: int = 50) -> list[Hit]:
    closes = [c["close"] for c in candles]
    f, s = sma(closes, fast), sma(closes, slow)
    out = []
    for i in range(1, len(candles)):
        if None in (f[i], s[i], f[i - 1], s[i - 1]):
            continue
        if f[i - 1] <= s[i - 1] and f[i] > s[i]:
            out.append(Hit(i, candles[i]["time"], "golden cross", {"fast": fast, "slow": slow}))
        elif f[i - 1] >= s[i - 1] and f[i] < s[i]:
            out.append(Hit(i, candles[i]["time"], "death cross", {"fast": fast, "slow": slow}))
    return out


def rsi_extremes(candles: list[Candle], overbought: bool = True, n: int = 14) -> list[Hit]:
    r = rsi([c["close"] for c in candles], n)
    out = []
    for i, v in enumerate(r):
        if v is None:
            continue
        if overbought and v >= 70 and (i == 0 or (r[i - 1] or 0) < 70):
            out.append(Hit(i, candles[i]["time"], "RSI overbought", {"rsi": round(v, 1)}))
        if not overbought and v <= 30 and (i == 0 or (r[i - 1] or 100) > 30):
            out.append(Hit(i, candles[i]["time"], "RSI oversold", {"rsi": round(v, 1)}))
    return out


def volume_spikes(candles: list[Candle], n: int = 20, mult: float = 2.5) -> list[Hit]:
    out = []
    for i in range(n, len(candles)):
        avg = sum(c["volume"] for c in candles[i - n: i]) / n
        if avg > 0 and candles[i]["volume"] > avg * mult:
            out.append(Hit(i, candles[i]["time"], "volume spike", {"ratio": round(candles[i]["volume"] / avg, 1)}))
    return out


# --------------------------------------------------------------------------- chart patterns (from swing points)
def _swings(candles: list[Candle], lookback: int = 3) -> list[Hit]:
    highs, lows = swing_points(candles, lookback)
    for h in highs:
        h.extra["kind"] = "high"
    for l in lows:
        l.extra["kind"] = "low"
    return sorted(highs + lows, key=lambda h: h.index)


def double_top(candles: list[Candle], tolerance: float = 0.004) -> list[Hit]:
    """Two swing highs at about the same price with a lower swing low between them (the neckline). Confirmed on a close below the neckline."""
    sw = _swings(candles)
    out = []
    for i in range(2, len(sw)):
        a, m, b = sw[i - 2], sw[i - 1], sw[i]
        if a.extra["kind"] == "high" and m.extra["kind"] == "low" and b.extra["kind"] == "high":
            pa, pb, neck = a.extra["price"], b.extra["price"], m.extra["price"]
            if abs(pa - pb) / pb <= tolerance and neck < min(pa, pb) * (1 - tolerance):
                confirmed = any(c["close"] < neck for c in candles[b.index + 1:b.index + 25])
                out.append(Hit(b.index, b.time, "double top", {"p1": pa, "p2": pb, "neckline": neck, "t1": a.time, "tm": m.time, "t2": b.time, "state": "confirmed" if confirmed else "forming", "invalidation": max(pa, pb)}))
    return out


def double_bottom(candles: list[Candle], tolerance: float = 0.004) -> list[Hit]:
    sw = _swings(candles)
    out = []
    for i in range(2, len(sw)):
        a, m, b = sw[i - 2], sw[i - 1], sw[i]
        if a.extra["kind"] == "low" and m.extra["kind"] == "high" and b.extra["kind"] == "low":
            pa, pb, neck = a.extra["price"], b.extra["price"], m.extra["price"]
            if abs(pa - pb) / pb <= tolerance and neck > max(pa, pb) * (1 + tolerance):
                confirmed = any(c["close"] > neck for c in candles[b.index + 1:b.index + 25])
                out.append(Hit(b.index, b.time, "double bottom", {"p1": pa, "p2": pb, "neckline": neck, "t1": a.time, "tm": m.time, "t2": b.time, "state": "confirmed" if confirmed else "forming", "invalidation": min(pa, pb)}))
    return out


def head_shoulders(candles: list[Candle], inverse: bool = False, tolerance: float = 0.006) -> list[Hit]:
    """Three peaks, the middle one highest, shoulders at about the same height; neckline through the two troughs."""
    sw = _swings(candles)
    peak, trough = ("low", "high") if inverse else ("high", "low")
    out = []
    for i in range(4, len(sw)):
        ls, t1, hd, t2, rs = sw[i - 4:i + 1]
        if [x.extra["kind"] for x in (ls, t1, hd, t2, rs)] != [peak, trough, peak, trough, peak]:
            continue
        pl, ph, pr = ls.extra["price"], hd.extra["price"], rs.extra["price"]
        higher = (ph < min(pl, pr)) if inverse else (ph > max(pl, pr))
        if not higher or abs(pl - pr) / pr > tolerance * 2:
            continue
        neck = (t1.extra["price"] + t2.extra["price"]) / 2
        confirmed = any((c["close"] > neck) if inverse else (c["close"] < neck) for c in candles[rs.index + 1:rs.index + 25])
        out.append(Hit(rs.index, rs.time, "inverse head and shoulders" if inverse else "head and shoulders",
                       {"points": [(x.time, x.extra["price"]) for x in (ls, t1, hd, t2, rs)], "neckline": neck, "state": "confirmed" if confirmed else "forming",
                        "invalidation": ph, "labels": ["LS", "", "H", "", "RS"]}))
    return out


def triangle(candles: list[Candle], min_swings: int = 4) -> list[Hit]:
    """Converging swing highs and lows (symmetrical / ascending / descending) over the last swings."""
    sw = _swings(candles)
    if len(sw) < min_swings + 1:
        return []
    seg = sw[-(min_swings + 1):]
    highs = [x for x in seg if x.extra["kind"] == "high"]
    lows = [x for x in seg if x.extra["kind"] == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return []
    hs = (highs[-1].extra["price"] - highs[0].extra["price"]) / max(1, highs[-1].index - highs[0].index)
    ls = (lows[-1].extra["price"] - lows[0].extra["price"]) / max(1, lows[-1].index - lows[0].index)
    ref = candles[-1]["close"]
    flat = ref * 0.0004
    if hs < -flat and ls > flat:
        kind = "symmetrical triangle"
    elif abs(hs) <= flat and ls > flat:
        kind = "ascending triangle"
    elif hs < -flat and abs(ls) <= flat:
        kind = "descending triangle"
    else:
        return []
    last = seg[-1]
    width_now = abs((highs[0].extra["price"] + hs * (last.index - highs[0].index)) - (lows[0].extra["price"] + ls * (last.index - lows[0].index)))
    width_start = abs(highs[0].extra["price"] - lows[0].extra["price"])
    if width_now >= width_start:
        return []
    upper = highs[0].extra["price"] + hs * (len(candles) - 1 - highs[0].index)
    lower = lows[0].extra["price"] + ls * (len(candles) - 1 - lows[0].index)
    broke_up = candles[-1]["close"] > upper
    broke_dn = candles[-1]["close"] < lower
    return [Hit(last.index, last.time, kind, {"points": [(x.time, x.extra["price"]) for x in seg], "upper": upper, "lower": lower,
                                             "state": "confirmed" if (broke_up or broke_dn) else "forming", "break": "up" if broke_up else "down" if broke_dn else ""})]


def bollinger_squeeze(candles: list[Candle], n: int = 20, lookback: int = 100) -> list[Hit]:
    """Band width at a lookback low: compression that tends to precede expansion (direction unknown)."""
    closes = [c["close"] for c in candles]
    m = sma(closes, n)
    widths: list[float | None] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        seg = closes[i - n + 1:i + 1]
        mu = sum(seg) / n
        sd = (sum((x - mu) ** 2 for x in seg) / n) ** 0.5
        widths[i] = 4 * sd / mu if mu else None
    out = []
    for i in range(n - 1 + lookback, len(closes)):
        window = [w for w in widths[i - lookback:i] if w is not None]
        if widths[i] is not None and window and widths[i] <= min(window) * 1.02:
            out.append(Hit(i, candles[i]["time"], "bollinger squeeze", {"width_pct": round(widths[i] * 100, 2), "mid": m[i]}))
    return out


def rsi_divergence(candles: list[Candle], n: int = 14, lookback: int = 3) -> list[Hit]:
    """Price makes a higher high while RSI makes a lower high (bearish), or the mirror (bullish)."""
    r = rsi([c["close"] for c in candles], n)
    highs, lows = swing_points(candles, lookback)
    out = []
    for arr, bear in ((highs, True), (lows, False)):
        for i in range(1, len(arr)):
            a, b = arr[i - 1], arr[i]
            ra, rb = r[a.index], r[b.index]
            if ra is None or rb is None or b.index - a.index > 60:
                continue
            pa, pb = a.extra["price"], b.extra["price"]
            if bear and pb > pa and rb < ra - 2:
                out.append(Hit(b.index, b.time, "bearish divergence", {"t1": a.time, "p1": pa, "t2": b.time, "p2": pb, "rsi1": round(ra, 1), "rsi2": round(rb, 1), "invalidation": pb}))
            if not bear and pb < pa and rb > ra + 2:
                out.append(Hit(b.index, b.time, "bullish divergence", {"t1": a.time, "p1": pa, "t2": b.time, "p2": pb, "rsi1": round(ra, 1), "rsi2": round(rb, 1), "invalidation": pb}))
    return out


def vwap_cross(candles: list[Candle]) -> list[Hit]:
    """Close crossing the session (UTC day) VWAP."""
    out = []
    pv = vv = 0.0
    day = None
    prev = None
    for i, c in enumerate(candles):
        d = c["time"] // 86400
        if d != day:
            day, pv, vv, prev = d, 0.0, 0.0, None
        v = c.get("volume") or 1.0
        pv += (c["high"] + c["low"] + c["close"]) / 3 * v
        vv += v
        vwap = pv / vv
        side = c["close"] > vwap
        if prev is not None and side != prev:
            out.append(Hit(i, c["time"], "vwap reclaim" if side else "vwap loss", {"vwap": round(vwap, 4)}))
        prev = side
    return out


SCANNERS = {
    "double_top": double_top,
    "double_bottom": double_bottom,
    "head_shoulders": lambda c: head_shoulders(c, False),
    "inv_head_shoulders": lambda c: head_shoulders(c, True),
    "triangle": triangle,
    "bollinger_squeeze": bollinger_squeeze,
    "rsi_divergence": rsi_divergence,
    "vwap_cross": vwap_cross,
    "engulfing_bull": lambda c: engulfing(c, True),
    "engulfing_bear": lambda c: engulfing(c, False),
    "pin_bar_bull": lambda c: pin_bar(c, True),
    "pin_bar_bear": lambda c: pin_bar(c, False),
    "doji": doji,
    "inside_bar": inside_bar,
    "swing_low": lambda c: swing_points(c)[1],
    "swing_high": lambda c: swing_points(c)[0],
    "support_level": lambda c: [h for h in levels(c) if h.label.startswith("support")],
    "resistance_level": lambda c: [h for h in levels(c) if h.label.startswith("resistance")],
    "breakout_up": lambda c: breakouts(c, up=True),
    "breakout_down": lambda c: breakouts(c, up=False),
    "higher_highs": higher_highs_lows,
    "lower_lows": lower_highs_lows,
    "range": ranges,
    "sma_cross": sma_cross,
    "rsi_overbought": lambda c: rsi_extremes(c, True),
    "rsi_oversold": lambda c: rsi_extremes(c, False),
    "volume_spike": volume_spikes,
}


def scan(name: str, candles: list[Candle]) -> list[Hit]:
    fn = SCANNERS.get(name)
    return fn(candles) if fn else []
