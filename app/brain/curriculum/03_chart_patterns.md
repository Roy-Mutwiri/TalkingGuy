---
module: chart_patterns
title: Chart patterns
level: beginner
---

# Chart patterns

## Teaching voice
Chart patterns are just market structure with a nickname. Teach each one by showing the swings that build it, then the level whose break completes it. Say plainly that patterns fail often, that the "measured move" is a rough guide not a target, and that the pattern's usefulness is mainly in giving a clear invalidation point. Context first, pattern second.

## Lessons
### double_bottom: Double bottom
- key points: Two swing lows in roughly the same zone with a swing high between them (the neckline). The pattern completes on a close above the neckline, not when the second low prints. The second low often wicks slightly below the first, trapping sellers. Invalidation is a close below the lows.
- common mistakes: Buying the second low before any reclaim. Expecting exact symmetry.
- best example: crypto, BTCUSDT, 4h, two swing lows within about 1-2% of each other, separated by 8+ candles, then a close above the middle swing high.
- pattern_scanner: swing_low
- on_screen_takeaway: A double bottom is confirmed by the neckline break, not by the second low.

### double_top: Double top
- key points: Two swing highs in the same zone with a swing low between them. Completes on a close below that swing low. Often the second high fails faster than the first, showing weaker demand. Invalidation is a close above the highs.
- common mistakes: Shorting the second high without a reclaim failure. Ignoring the higher-timeframe uptrend.
- best example: stock, TSLA, 1d, two swing highs within a narrow band, then a close below the middle swing low.
- pattern_scanner: swing_high
- on_screen_takeaway: A double top is a failed second attempt; the neckline close is the confirmation.

### head_and_shoulders: Head and shoulders
- key points: Three peaks, the middle one highest, with a neckline connecting the two troughs. It describes a trend losing momentum: the right shoulder fails to make a new high. Completes on a neckline close. The pattern fails when price reclaims the right shoulder high.
- common mistakes: Seeing head and shoulders everywhere. Entering before the neckline break.
- best example: forex, EURUSD, 4h, a higher high followed by a lower high with a shared support area beneath.
- pattern_scanner: lower_lows
- on_screen_takeaway: Head and shoulders is a story of a lower high. The neckline close tells you the story ended.

### triangles: Triangles and contraction
- key points: Ascending, descending and symmetrical triangles are all contraction: swings getting smaller. An ascending triangle has a flat top and rising lows, descending is the mirror, symmetrical converges from both sides. Direction of the break is not guaranteed by the shape. The invalidation is a close back inside after a break.
- common mistakes: Assuming ascending means up. Drawing lines through wicks to force the shape.
- best example: crypto, ETHUSDT, 4h, at least three touches on each side with narrowing swings over 30+ candles.
- pattern_scanner: range
- on_screen_takeaway: Triangles show contraction. The break resolves it; the shape does not predict the direction.

### flags_pennants: Flags and pennants
- key points: A sharp move (the pole) followed by a small, orderly pullback (the flag). The flag drifts against the pole direction on falling volume. The pattern completes on a break of the flag in the pole direction. A move beyond the opposite side of the flag invalidates it.
- common mistakes: Calling any pullback a flag. Trading flags that are larger than the pole.
- best example: stock, NVDA, 1h, a strong directional move of 10+ candles followed by a tight 5-10 candle pullback.
- pattern_scanner: breakout_up
- on_screen_takeaway: A flag is a rest after a run. The break in the pole direction is the signal to study.

### wedges: Rising and falling wedges
- key points: A wedge has both boundaries sloping the same way and converging. Rising wedges show momentum fading on each push up; falling wedges show selling slowing. The break usually comes against the slope but that is a tendency, not a rule. Invalidation is a close beyond the far boundary.
- common mistakes: Confusing a wedge with a channel. Fading a wedge in a strong trend.
- best example: crypto, SOLUSDT, 4h, three or more higher highs with each push smaller than the last, converging lines.
- pattern_scanner: higher_highs
- on_screen_takeaway: Wedges show momentum running out of room. Wait for the break and respect the invalidation.

### pattern_failure: When patterns fail
- key points: Failed patterns are information: a failed breakout traps traders on the wrong side and often moves fast the other way. Treat every pattern as a hypothesis with a clear invalidation. The failure point is defined before the trade, not after. Measured moves are rough guides, never guarantees.
- common mistakes: Holding through the invalidation hoping the pattern still works. Blaming the pattern instead of the plan.
- best example: forex, GBPUSD, 1h, a breakout above a range high that closes back inside within 3 candles.
- pattern_scanner: breakout_up
- on_screen_takeaway: Patterns are hypotheses. The invalidation level is the most useful part of any pattern.
