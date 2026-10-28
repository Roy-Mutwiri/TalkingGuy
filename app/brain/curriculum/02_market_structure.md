---
module: market_structure
title: Support, resistance and market structure
level: beginner
---

# Support, resistance and market structure

## Teaching voice
Teach structure as the map, before any pattern or indicator. Show real swing highs and swing lows on the chart and let the viewer see the sequence forming. Be honest: levels are zones, not exact prices, and they break all the time. The goal is to know where the market is in its story, not to predict the next chapter.

## Lessons
### swing_highs_lows: Swing highs and swing lows
- key points: A swing high is a candle high with lower highs on both sides; a swing low is the mirror. They are the pivots the market turns at. Mark them on a clean chart before anything else. Bigger timeframes give more important swings.
- common mistakes: Marking every tiny wiggle. Using a different definition each day.
- best example: crypto, BTCUSDT, 4h, a stretch with 3-4 clear swing highs and swing lows, each separated by at least 5 candles.
- pattern_scanner: swing_low
- on_screen_takeaway: Swings are the market's footprints. Mark them first, then read the sequence.

### uptrend_structure: Higher highs and higher lows
- key points: An uptrend is a sequence of higher highs and higher lows. The most recent higher low is the line in the sand: if price closes below it, the sequence is broken. Pullbacks to a prior swing area are where many traders look for continuation. The trend is a description of the past, not a guarantee.
- common mistakes: Calling an uptrend after one higher high. Ignoring the higher low that just failed.
- best example: stock, AAPL, 1d, at least three consecutive higher highs and higher lows over 30-60 days.
- pattern_scanner: higher_highs
- on_screen_takeaway: An uptrend lives while higher lows hold. The last higher low is the invalidation.

### downtrend_structure: Lower highs and lower lows
- key points: A downtrend is a sequence of lower highs and lower lows. The most recent lower high is where the structure would flip if broken. Rallies into a prior swing area are where sellers often reappear. Downtrends can end slowly through a range or sharply through a reclaim.
- common mistakes: Buying the first green candle in a downtrend. Confusing a pullback with a reversal.
- best example: crypto, ETHUSDT, 4h, at least three consecutive lower highs and lower lows.
- pattern_scanner: lower_lows
- on_screen_takeaway: A downtrend lives while lower highs hold. Watch the last lower high.

### support_zones: Support as a zone
- key points: Support is an area where buyers showed up before, visible as prior swing lows or a cluster of closes. Draw it as a zone, not a line. The more times a level holds, the more traders watch it, and the more obvious the eventual break. A clean break and close below turns the zone into resistance.
- common mistakes: Drawing lines at exact wicks. Assuming support must hold because it held before.
- best example: forex, XAUUSD, 4h, a price area touched at least twice as a low before a reaction.
- pattern_scanner: support_level
- on_screen_takeaway: Support is a zone where buyers acted before. It holds until it doesn't, so plan for both.

### resistance_zones: Resistance as a zone
- key points: Resistance is an area where sellers showed up before: prior swing highs, old breakdown points, round numbers. Price often stalls there because trapped buyers sell to get out. A break and close above with follow-through flips the zone to support. Failed breaks are common and informative.
- common mistakes: Shorting at resistance in a strong trend without any sign of rejection. Ignoring the candle close.
- best example: stock, SPY, 1d, a price area that capped price at least twice before.
- pattern_scanner: resistance_level
- on_screen_takeaway: Resistance is where sellers acted before. The close through it matters more than the poke.

### break_of_structure: Break of structure and the flip
- key points: A break of structure is a close beyond the most recent swing in the opposite direction of the trend. It does not prove a reversal; it means the old sequence stopped. The next swing tells you whether a new sequence starts. Old support becoming resistance (and vice versa) is the flip to watch.
- common mistakes: Treating a wick through a level as a break. Calling a reversal before a new swing confirms it.
- best example: crypto, SOLUSDT, 4h, a close below the last higher low after a clear uptrend, then a retest of that area from below.
- pattern_scanner: breakout_down
- on_screen_takeaway: A break of structure ends the old sequence. It takes a new swing to start the next one.

### ranges: Ranges and sideways markets
- key points: A range is price oscillating between a support zone and a resistance zone with no new swings beyond them. Most of the time markets are ranging, not trending. The edges are where decisions are made; the middle is noise. Breakouts from ranges often fail once before they work.
- common mistakes: Trend-following in the middle of a range. Chasing the first breakout.
- best example: forex, USDJPY, 1h, at least 40 candles bouncing between two zones with no new high or low.
- pattern_scanner: range
- on_screen_takeaway: In a range, the edges carry information and the middle carries risk.
