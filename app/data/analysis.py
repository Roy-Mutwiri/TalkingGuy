"""Deep chart analysis: turns a candle series into a trader's draft-book markup plus short
narration lines. Output is a list of "steps", each a chart action dict (see schema.py) with an
optional "say" sentence, in the order a trader would actually draw them:

  structure (swing labels HH/HL/LH/LL) -> trendline/channel -> support & resistance zones ->
  Fibonacci on the last impulse -> liquidity (equal highs/lows) -> fair value gaps -> order blocks
  -> moving averages -> session/day high-low -> measured move -> notes

Everything is computed from price only; nothing here predicts. Narration describes what is on
the chart and where an idea would be wrong.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import patterns
from .store import Candle


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _spoken(p: float) -> str:
    if p >= 10000:
        return f"{round(p, -1):,.0f}"
    if p >= 100:
        return f"{p:,.1f}" if p < 1000 else f"{p:,.0f}"
    return f"{p:.2f}" if p >= 1 else f"{p:.4f}"


def _ema(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    e = sum(values[:n]) / n
    out[n - 1] = e
    for i in range(n, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def _pattern_step(candles: list[Candle]) -> dict | None:
    """The most recent recognisable chart pattern, drawn with its honest state (forming / confirmed) and its neckline."""
    tries = (("head_shoulders", "head_shoulders"), ("inv_head_shoulders", "inv_head_shoulders"), ("double_top", "double_top"),
             ("double_bottom", "double_bottom"), ("triangle", "triangle"))
    best = None
    for scanner, kind in tries:
        hits = patterns.scan(scanner, candles)
        if hits and (best is None or hits[-1].index > best[0].index):
            best = (hits[-1], kind)
    if best is None or len(candles) - 1 - best[0].index > 80:
        return None
    h, kind = best
    ex = h.extra
    if "points" in ex:
        pts = [{"time": _iso(t), "price": p} for t, p in ex["points"]]
        k = kind if kind != "triangle" else ("triangle" if "triangle" in h.label else "wedge")
    else:
        pts = [{"time": _iso(ex["t1"]), "price": ex["p1"]}, {"time": _iso(ex["tm"]), "price": ex["neckline"]}, {"time": _iso(ex["t2"]), "price": ex["p2"]}]
        k = kind
    state = ex.get("state", "forming")
    what = h.label
    neck = ex.get("neckline")
    say = (f"A {what}, still forming. The outline is dashed on purpose: until a candle closes through the neckline it is a shape, not a pattern."
           if state == "forming" else
           f"A {what}, confirmed by a close through the neckline. Now the question is the retest, and the invalidation is back inside the pattern.")
    return {"action": "pattern", "id": "pat", "kind": k, "points": pts, "neckline": neck, "labels": ex.get("labels"), "label": what, "state": state, "color": "#e879f9", "say": say}


def analyze(candles: list[Candle], symbol: str = "", max_steps: int = 48) -> list[dict]:
    """Return ordered markup steps for the given candles (needs ~60+ bars)."""
    n = len(candles)
    if n < 30:
        return []
    steps: list[dict] = []
    say = lambda s: s  # noqa: E731
    step_s = candles[1]["time"] - candles[0]["time"] if n > 1 else 60
    closes = [c["close"] for c in candles]
    last = candles[-1]
    tol = 0.0025 if last["close"] > 100 else 0.0035

    # ---- 1. structure: swing points with HH/HL/LH/LL labels ------------------------
    highs, lows = patterns.swing_points(candles, lookback=3)
    highs, lows = highs[-6:], lows[-6:]
    labels = []
    for i, h in enumerate(highs):
        if i == 0:
            continue
        labels.append((h.time, "HH" if h.extra["price"] > highs[i - 1].extra["price"] else "LH", "aboveBar", "#f56565" if h.extra["price"] <= highs[i - 1].extra["price"] else "#22c55e"))
    for i, l in enumerate(lows):
        if i == 0:
            continue
        labels.append((l.time, "HL" if l.extra["price"] > lows[i - 1].extra["price"] else "LL", "belowBar", "#22c55e" if l.extra["price"] > lows[i - 1].extra["price"] else "#f56565"))
    labels.sort()
    trend = "up" if labels and sum(1 for _, t, _, _ in labels[-4:] if t in ("HH", "HL")) >= 3 else "down" if labels and sum(1 for _, t, _, _ in labels[-4:] if t in ("LH", "LL")) >= 3 else "range"
    for k, (t, tag, pos, col) in enumerate(labels[-6:]):
        steps.append({"action": "marker", "id": f"sw{k}", "time": _iso(t), "text": tag, "position": pos, "shape": "circle", "color": col,
                      "say": (f"Structure first. I mark every swing: higher highs, higher lows, or the opposite. Right now the sequence reads {trend}." if k == 0 else None)})
    # structure path through swings (zig-zag)
    pts = sorted([(h.time, h.extra["price"]) for h in highs] + [(l.time, l.extra["price"]) for l in lows])
    if len(pts) >= 3:
        steps.append({"action": "path", "id": "zigzag", "points": [{"time": _iso(t), "price": p} for t, p in pts[-8:]], "color": "#f5c542", "width": 2, "dashed": True,
                      "say": "That zig-zag is the skeleton of the move. Everything else hangs on it."})

    # ---- 2. trendline / channel on the last swings --------------------------------
    anchors = lows if trend == "up" else highs if trend == "down" else None
    if anchors and len(anchors) >= 2:
        a, b = anchors[-2], anchors[-1]
        steps.append({"action": "trendline", "id": "trend", "t1": _iso(a.time), "p1": a.extra["price"], "t2": _iso(b.time), "p2": b.extra["price"], "label": "trend", "color": "#f56565" if trend == "down" else "#22c55e", "extend": True,
                      "say": f"Trendline through the last two swing {'lows' if trend == 'up' else 'highs'}. A close through it is the first warning that the structure is changing."})
        others = highs if trend == "up" else lows
        if len(others) >= 2:
            o1, o2 = others[-2], others[-1]
            steps.append({"action": "trendline", "id": "chan", "t1": _iso(o1.time), "p1": o1.extra["price"], "t2": _iso(o2.time), "p2": o2.extra["price"], "label": "channel", "color": "#f5c542", "extend": True,
                          "say": "And the other side of the channel. Price lives between these two lines until it doesn't."})

    # ---- 3. support / resistance zones --------------------------------------------
    lv = patterns.levels(candles, lookback=3, tolerance=tol)
    lv = sorted(lv, key=lambda h: -h.extra["touches"])[:3]
    for i, h in enumerate(lv):
        p = h.extra["price"]
        band = p * (0.0012 if p > 100 else 0.0018)
        kind = "support" if h.label.startswith("support") else "resistance"
        steps.append({"action": "zone", "id": f"zone{i}", "top": p + band, "bottom": p - band, "label": f"{kind} x{h.extra['touches']}", "color": "rgba(79,209,197,0.22)" if kind == "support" else "rgba(245,197,66,0.22)",
                      "say": (f"Zones, not lines. This {kind} around {_spoken(p)} was touched {h.extra['touches']} times. The more touches, the more the market remembers it." if i == 0 else None)})

    # ---- 4. Fibonacci on the last impulse ----------------------------------------
    if highs and lows:
        h, l = highs[-1], lows[-1]
        up_leg = l.time < h.time
        start, end = (l, h) if up_leg else (h, l)
        steps.append({"action": "fib", "id": "fib", "t1": _iso(start.time), "p1": start.extra["price"], "t2": _iso(end.time), "p2": end.extra["price"],
                      "levels": [0.382, 0.5, 0.618, 0.786], "color": "#a78bfa",
                      "say": f"Fib on the last {'rally' if up_leg else 'drop'}, from {_spoken(start.extra['price'])} to {_spoken(end.extra['price'])}. I only care if a retracement lands on a level that already mattered. A fib alone is a coincidence; a fib on a zone is a confluence."})

    # ---- 5. liquidity: equal highs / equal lows ----------------------------------
    eq = []
    for arr, kind in ((highs, "equal highs"), (lows, "equal lows")):
        for i in range(1, len(arr)):
            a, b = arr[i - 1], arr[i]
            if abs(a.extra["price"] - b.extra["price"]) / b.extra["price"] < tol * 0.6:
                eq.append((kind, a, b))
    for kind, a, b in eq[:2]:
        steps.append({"action": "hline", "price": (a.extra["price"] + b.extra["price"]) / 2, "label": kind, "color": "#f97316", "style": "dotted",
                      "say": f"{kind.capitalize()} here. Stops sit behind them, so expect price to poke through before it decides. That is liquidity, not a level."})

    # ---- 6. fair value gaps (3-candle imbalance) in the last 60 bars --------------
    fvg = []
    for i in range(max(2, n - 60), n):
        a, c = candles[i - 2], candles[i]
        if c["low"] > a["high"] and (c["low"] - a["high"]) / a["high"] > tol * 0.5:
            fvg.append(("bullish", candles[i - 1]["time"], a["high"], c["low"]))
        elif c["high"] < a["low"] and (a["low"] - c["high"]) / a["low"] > tol * 0.5:
            fvg.append(("bearish", candles[i - 1]["time"], c["high"], a["low"]))
    for k, (kind, t, lo, hi) in enumerate(fvg[-2:]):
        steps.append({"action": "rect", "t1": _iso(t), "t2": _iso(min(last["time"], t + step_s * 25)), "top": hi, "bottom": lo, "label": f"{kind} FVG", "color": "rgba(167,139,250,0.25)",
                      "say": (f"Gap in the candles, a {kind} imbalance. Price moved so fast nobody traded there. Those gaps often get revisited; they are not magnets, they are unfinished business." if k == 0 else None)})

    # ---- 7. order block: last opposite candle before the biggest impulse --------
    best = None
    for i in range(max(3, n - 80), n - 3):
        move = (candles[i + 3]["close"] - candles[i]["open"]) / candles[i]["open"]
        if best is None or abs(move) > abs(best[1]):
            best = (i, move)
    if best and abs(best[1]) > tol * 3:
        i, move = best
        ob = None
        for j in range(i, max(0, i - 6), -1):
            c = candles[j]
            if (move > 0 and c["close"] < c["open"]) or (move < 0 and c["close"] > c["open"]):
                ob = c
                break
        if ob:
            steps.append({"action": "rect", "t1": _iso(ob["time"]), "t2": _iso(min(last["time"], ob["time"] + step_s * 40)), "top": max(ob["open"], ob["close"]), "bottom": min(ob["open"], ob["close"]),
                          "label": f"{'bullish' if move > 0 else 'bearish'} OB", "color": "rgba(34,197,94,0.22)" if move > 0 else "rgba(245,101,101,0.22)",
                          "say": f"The last {'red' if move > 0 else 'green'} candle before that impulse. Some call it an order block. I call it the place where the move was decided. If price returns there, I want to see a reaction."})

    # ---- 8. moving averages -----------------------------------------------------
    for span, col, name in ((20, "#38bdf8", "EMA 20"), (50, "#f59e0b", "EMA 50")):
        e = _ema(closes, span)
        pts = [{"time": _iso(candles[i]["time"]), "value": v} for i, v in enumerate(e) if v is not None]
        if pts:
            steps.append({"action": "indicator", "id": name.replace(" ", "").lower(), "name": name, "points": pts[-150:], "color": col,
                          "say": (f"Two averages, twenty and fifty, just to see the slope. Price {'above' if closes[-1] > (pts[-1]['value']) else 'below'} the twenty right now." if span == 20 else None)})

    # ---- 9. day high / low, measured move ----------------------------------------
    day = [c for c in candles if c["time"] >= last["time"] - 86400] or candles[-24:]
    dh, dl = max(c["high"] for c in day), min(c["low"] for c in day)
    steps.append({"action": "hline", "id": "dh", "price": dh, "label": "day high", "color": "#f56565", "style": "dashed"})
    steps.append({"action": "hline", "id": "dl", "price": dl, "label": "day low", "color": "#4fd1c5", "style": "dashed",
                  "say": f"Day high {_spoken(dh)}, day low {_spoken(dl)}. Where we sit inside that range tells you who has been winning today."})
    if highs and lows:
        h, l = highs[-1], lows[-1]
        leg = abs(h.extra["price"] - l.extra["price"])
        base = last["close"]
        up = closes[-1] > closes[-10] if n > 10 else True
        steps.append({"action": "arrow", "id": "mm", "t1": _iso(last["time"] - step_s * 6), "p1": base, "t2": _iso(last["time"]), "p2": base + (leg if up else -leg), "label": "measured move", "color": "#e879f9",
                      "say": f"Measured move: the size of the last leg projected from here, about {_spoken(leg)} {'up' if up else 'down'}. Not a target. A ruler, so a move has a sense of scale."})

    # ---- 9b. the chartist's extra tools: regression channel, anchored VWAP, fixed-range profile, key levels,
    #          session, chart pattern with its state, a position ruler, Bollinger context -------------------
    if n >= 60:
        steps.append({"action": "regression", "id": "regr", "start": _iso(candles[max(0, n - 60)]["time"]), "end": _iso(last["time"]), "deviations": 2.0, "label": "regression",
                      "color": "#2962ff",
                      "say": "A regression channel over the last sixty bars. The middle line is the average path, the bands are two standard deviations. Price at a band is stretched, not finished."})
    if highs and lows:
        anchor = lows[-1] if trend == "up" else highs[-1]
        if n - 1 - anchor.index >= 3:
            steps.append({"action": "avwap", "id": "avwap", "anchor": _iso(anchor.time), "label": "AVWAP", "color": "#ff9800",
                          "say": f"Anchored VWAP from the last swing {'low' if trend == 'up' else 'high'}. It is the average price everyone paid since that turn. Above it buyers are in profit; below it they are not."})
    if n >= 40:
        steps.append({"action": "vprofile", "id": "vprof", "start": _iso(candles[max(0, n - 60)]["time"]), "end": _iso(last["time"]), "rows": 24, "label": "60-bar profile",
                      "say": "Volume by price over the same sixty bars. The fat part is where business was done, the point of control is the fairest price, the thin parts were fast moves."})
    steps.append({"action": "keylevels", "id": "keys", "which": ["pdh", "pdl", "dopen"],
                  "say": "Previous day high and low, and today's open. Three levels every desk watches, so they are where reactions cluster."})
    hour = datetime.fromtimestamp(last["time"], timezone.utc).hour
    sess = "newyork" if 12 <= hour < 21 else "london" if 7 <= hour < 12 else "asia"
    steps.append({"action": "session", "id": "sess", "name": sess, "levels": True,
                  "say": f"The {'New York' if sess == 'newyork' else 'London' if sess == 'london' else 'Asian'} session shaded, with its high and low. Session extremes are the most common stop-run targets of the next session."})
    pat = _pattern_step(candles)
    if pat:
        steps.append(pat)
    if lv and highs and lows:
        # a worked position example anchored on the nearest zone: a ruler for risk, said out loud as not-a-signal
        p0 = lv[0].extra["price"]
        long = p0 < last["close"]
        risk = max(abs(last["close"] - p0) * 0.5, last["close"] * 0.002)
        entry = p0 + (risk * 0.3 if long else -risk * 0.3)
        stop = entry - risk if long else entry + risk
        target = entry + 2 * risk if long else entry - 2 * risk
        steps.append({"action": "position", "id": "pos", "side": "long" if long else "short", "time": _iso(candles[max(0, n - 12)]["time"]), "entry": entry, "stop": stop, "target": target, "risk_pct": 1.0,
                      "label": "example only", "state": "forming",
                      "say": f"The position tool, as an example of how risk is measured, not as a trade. If someone bought near that zone with the stop beyond it, the risk is the red box and the green box is two times that. One percent of the account on the red box, and the size follows from the distance."})
    if n >= 40:
        steps.append({"action": "study", "id": "bb", "kind": "bollinger", "length": 20, "mult": 2.0, "color": "#787b86",
                      "say": "Bollinger bands, twenty and two. Tight bands mean the market is coiled; a close outside a band is a stretch, not a reversal."})
        steps.append({"action": "study", "id": "rsi", "kind": "rsi", "length": 14, "color": "#7e57c2",
                      "say": "RSI fourteen in its own pane. I read it for divergence, not for overbought and oversold, which just means strong trend."})

    # ---- 10. notes -----------------------------------------------------------------
    pos = (last["close"] - dl) / max(1e-9, dh - dl)
    note = ("Pressing the highs. Needs acceptance above, not a wick." if pos > 0.8 else
            "Sitting on the lows. Watch for a sweep and reclaim, or a clean break." if pos < 0.2 else
            "Middle of the range. No edge here. Wait for the edges.")
    steps.append({"action": "note", "time": _iso(last["time"] - step_s * 12), "price": dh + (dh - dl) * 0.04, "text": note, "color": "#f5c542",
                  "say": f"Written on the chart so I hold myself to it: {note.lower()}"})
    steps.append({"action": "note", "time": _iso(candles[max(0, n - 40)]["time"]), "price": dl - (dh - dl) * 0.04, "text": f"invalidation: {'below ' + _spoken(lows[-1].extra['price']) if trend == 'up' and lows else 'above ' + _spoken(highs[-1].extra['price']) if highs else 'n/a'}", "color": "#f56565",
                  "say": "And the invalidation, written where I can see it. If price trades through it, the whole sheet is wrong and I start again."})
    # layers: what stays on the chart (keep) and what is a passing illustration (transient, cleared when the next
    # transient layer starts) so the markup reads as a sequence of clean slides instead of one pile of lines
    layer_of = {"marker": "structure", "path": "structure", "trendline": "trend", "zone": "levels", "fib": "fib", "hline": "levels",
                "rect": "gaps", "indicator": "averages", "arrow": "measure", "regression": "channel", "avwap": "avwap", "vprofile": "profile",
                "keylevels": "levels", "session": "session", "pattern": "pattern", "position": "position", "study": "studies", "note": "notes"}
    keep = {"trend", "levels", "pattern", "notes", "studies"}
    for st in steps:
        lay = layer_of.get(st["action"], "other")
        if st["action"] == "hline" and st.get("label", "") in ("equal highs", "equal lows"):
            lay = "liquidity"
        st["layer"] = lay
        st["keep"] = lay in keep
    return steps[:max_steps]
