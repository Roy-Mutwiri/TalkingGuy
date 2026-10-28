---
module: indicators
title: Indicators without the mythology
level: beginner
---

# Indicators without the mythology

## Teaching voice
Every indicator is a calculation on past price or volume. Say that clearly and often: indicators cannot see the future, they summarise the past. Teach what each one measures, show it on a real chart next to the candles, and show both a moment it helped and a moment it misled. Fewer indicators, understood deeply, beats a cluttered screen.

## Lessons
### moving_averages: What a moving average measures
- key points: A simple moving average is the average close of the last N candles; an exponential one weights recent candles more. It smooths noise and shows the direction of the average price. Price above a rising average describes an uptrend in that lookback. Averages lag by design.
- common mistakes: Treating the average as a magic support line. Stacking five averages and calling it analysis.
- best example: crypto, BTCUSDT, 1d, a trending stretch where price stays mostly above a 50-period average and pulls back to it twice.
- pattern_scanner: sma_cross
- on_screen_takeaway: A moving average is the average of the past. It describes the trend, it does not predict it.

### ma_crossovers: Moving average crossovers
- key points: A fast average crossing above a slow one says recent prices rose faster than older prices. It confirms a trend that already started. Crossovers whipsaw badly in ranges and shine in long trends. Use them to describe regime, not to time entries.
- common mistakes: Trading every crossover. Ignoring the many false crosses in sideways markets.
- best example: stock, AAPL, 1d, a 20/50 crossover at the start of a multi-month trend, plus a choppy range with several false crosses.
- pattern_scanner: sma_cross
- on_screen_takeaway: A crossover confirms a move already underway. In a range it mostly produces noise.

### rsi_basics: RSI: what it really tells you
- key points: RSI compares average gains to average losses over 14 periods, scaled 0-100. Above 70 means recent gains dominated; below 30 means losses dominated. In a strong trend RSI can stay above 70 for weeks, so "overbought" is not a sell signal. RSI is most useful as a momentum gauge and for spotting divergence.
- common mistakes: Shorting because RSI is 75. Using RSI without looking at the trend.
- best example: crypto, SOLUSDT, 4h, a strong rally where RSI stays above 70 for 10+ candles while price keeps rising.
- pattern_scanner: rsi_overbought
- on_screen_takeaway: Overbought means momentum is strong, not that price must fall.

### rsi_divergence: RSI divergence
- key points: Bearish divergence: price makes a higher high while RSI makes a lower high, showing momentum fading. Bullish divergence is the mirror at lows. Divergence can persist for a long time before anything happens. It is a context clue that needs a structural confirmation, such as a break of a swing.
- common mistakes: Entering on divergence alone. Drawing divergence between non-adjacent swings.
- best example: forex, EURUSD, 4h, a higher high in price with a lower RSI high, followed later by a break below the last swing low.
- pattern_scanner: swing_high
- on_screen_takeaway: Divergence says momentum is fading. Structure says when it matters.

### macd_basics: MACD: trend and momentum in one
- key points: MACD is the difference between two exponential averages, with a signal line and a histogram. The histogram shows whether momentum is accelerating or decelerating. Zero-line crosses roughly match moving average crossovers. It lags like any average-based tool.
- common mistakes: Reading histogram ticks on low timeframes as signals. Using MACD and two moving averages together, which is the same information twice.
- best example: stock, NVDA, 1d, a histogram shrinking for several bars while price still rises, then a clear turn.
- pattern_scanner: sma_cross
- on_screen_takeaway: MACD is moving averages in disguise. Use it to watch momentum fade or build, not to time entries.

### volume_indicator: Reading the volume bars
- key points: Volume is the number of units traded per candle. A spike shows interest, but not direction. Breakouts on expanding volume are more trusted than breakouts on thin volume. Climactic volume after a long move often marks exhaustion rather than continuation.
- common mistakes: Confusing high volume with bullishness. Comparing volume across different exchanges or sessions.
- best example: crypto, BTCUSDT, 4h, a breakout candle with volume at least twice the 20-candle average.
- pattern_scanner: volume_spike
- on_screen_takeaway: Volume measures participation, not direction. Read it with the candle, not instead of it.

### indicator_overload: Why fewer indicators work better
- key points: Most indicators derive from the same price and volume data, so stacking them adds confirmation bias, not information. Pick one trend tool, one momentum tool, and price structure. Every indicator has a setting; changing settings until it "works" on past data is curve fitting. The chart with fewer lines is usually the honest one.
- common mistakes: Adding an indicator after each losing trade. Trusting a signal because four correlated tools agree.
- best example: forex, XAUUSD, 1h, the same chart shown clean and then with several indicators to contrast readability.
- pattern_scanner: none
- on_screen_takeaway: Indicators summarise the past. Three correlated tools agreeing is one opinion, not three.

### fibonacci_retracement: Fibonacci retracement, without the mysticism
- key points: Draw the tool from the start to the end of one clear impulse, swing low to swing high in an uptrend. The 38.2, 50 and 61.8 percent lines mark how deep a pullback has gone. A fib level means nothing on its own; it matters when it lands on a level price already respected, a prior swing or a zone. The 78.6 percent line is the last stop before the whole leg is in doubt.
- common mistakes: Drawing fibs on every wiggle instead of one clear impulse. Treating a fib line as a wall. Entering because price touched 61.8 with no reaction and no invalidation.
- best example: forex, XAUUSD, 1h, a clean impulse of 20+ bars followed by a pullback that reacts between the 50 and 61.8 percent retracement near a prior swing.
- pattern_scanner: swing_low
- on_screen_takeaway: A fib level is a coincidence. A fib level on a zone is a confluence.
