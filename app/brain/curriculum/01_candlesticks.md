---
module: candlesticks
title: Candlesticks and price action
level: beginner
---

# Candlesticks and price action

## Teaching voice
Start from what a candle literally is: a summary of who won the fight between buyers and sellers during one block of time. Use real charts, name the open, high, low and close out loud, and keep reminding the viewer that a candle pattern is only as good as the location it prints at. Context first, pattern second. Never promise that a candle "means price will go up"; it only tells you what already happened.

## Lessons
### candle_anatomy: What a candlestick actually shows
- key points: A candle has four prices: open, high, low, close. The body is open-to-close, the wicks are the extremes. A green (or white) body means close above open; red means close below open. The timeframe sets how much time one candle covers.
- common mistakes: Thinking colour alone matters, ignoring the wicks. Reading a 1-minute candle as if it had the weight of a daily candle.
- best example: crypto, BTCUSDT, 4h, any stretch of 40-60 candles with a mix of big bodies and long wicks so each part can be pointed at.
- pattern_scanner: none
- on_screen_takeaway: A candle is a story of one time block: where it opened, how far it fought, and where it closed.

### wicks_and_rejection: Long wicks and rejection
- key points: A long wick shows price went somewhere and was pushed back. A long lower wick at a prior low shows buyers stepped in; a long upper wick at a prior high shows sellers stepped in. The close relative to the range tells you who finished in control. Wicks matter more at levels than in the middle of nowhere.
- common mistakes: Calling every wick a "rejection". Ignoring that the next candle can undo the wick.
- best example: forex, EURUSD, 1h, a long lower wick (pin bar) printed into a prior swing low after a pullback of at least 3 bars.
- pattern_scanner: pin_bar_bull
- on_screen_takeaway: A wick shows where price was refused. Its meaning depends on the level it printed at.

### bullish_engulfing: The bullish engulfing candle
- key points: A red candle followed by a green candle whose body closes above the red candle's open. It shows buyers absorbing the selling and pushing beyond it. Strongest after a pullback into support or a prior swing low. The low of the engulfing candle is the natural invalidation point.
- common mistakes: Trading every engulfing candle regardless of location. Measuring with wicks instead of bodies.
- best example: crypto, ETHUSDT, 4h, a bullish engulfing after a 3+ bar pullback into a prior swing low.
- pattern_scanner: engulfing_bull
- on_screen_takeaway: An engulfing candle only matters where buyers had a reason to show up.

### bearish_engulfing: The bearish engulfing candle
- key points: A green candle followed by a red candle whose body closes below the green candle's open. Sellers overwhelmed the buying. Most meaningful at resistance or after an extended rally. The high of the engulfing candle marks where the idea would be wrong.
- common mistakes: Shorting into strong uptrends on a single engulfing candle. Forgetting that a higher-timeframe trend can swallow the pattern.
- best example: stock, NVDA, 1d, a bearish engulfing at or just below a prior swing high after at least 5 up days.
- pattern_scanner: engulfing_bear
- on_screen_takeaway: A bearish engulfing at resistance says sellers showed up; the candle high is the invalidation.

### doji_and_indecision: Doji and indecision candles
- key points: A doji has a tiny body: open and close almost equal. It means neither side won that block of time. On its own it is noise; after a long directional run it can flag that momentum is slowing. Confirmation comes from the next candle, not the doji.
- common mistakes: Treating a doji as a reversal by itself. Spotting dojis inside a tight range where every candle is small.
- best example: forex, GBPUSD, 4h, a doji after at least 6 consecutive candles in one direction, followed by a candle in the other direction.
- pattern_scanner: doji
- on_screen_takeaway: A doji is a pause, not a decision. Wait for the next candle to say who won.

### inside_bar: Inside bars and compression
- key points: An inside bar sits fully within the previous candle's high-low range. It shows a contraction of volatility. Traders watch the break of the mother candle's high or low because compression often precedes expansion. The direction of the break is unknown in advance.
- common mistakes: Guessing the break direction. Using inside bars on very low timeframes where they appear constantly.
- best example: crypto, SOLUSDT, 1d, one or two inside bars after a strong trend day, then a break of the mother candle range.
- pattern_scanner: inside_bar
- on_screen_takeaway: Inside bars show compression. The break of the mother candle is the event, not the inside bar.

### candle_context: Why location beats pattern
- key points: The same candle at support, in the middle of a range, and at resistance tells three different stories. Always ask: where is this candle relative to recent highs, lows and the trend. A pattern in line with the higher-timeframe trend has more weight than one against it. Pattern recognition is the last step, not the first.
- common mistakes: Scanning for patterns without first marking levels. Zooming in so far the context disappears.
- best example: crypto, BTCUSDT, 4h, the same pin bar style candle appearing once at a prior swing low and once in the middle of a move, to contrast them.
- pattern_scanner: pin_bar_bull
- on_screen_takeaway: Mark the level first. Then ask what the candle at that level is telling you.
