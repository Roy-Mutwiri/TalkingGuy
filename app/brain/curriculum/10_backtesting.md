---
module: backtesting
title: Backtesting and the testing mindset
level: intermediate
---

# Backtesting and the testing mindset

## Teaching voice
Teach backtesting as the habit of checking ideas against history before trusting them with money. Keep it practical: scroll back on a real chart, apply the rule, write down what happened. Be honest that past results do not guarantee anything and that most ideas fail testing, which is exactly the point. The goal is to replace belief with evidence.

## Lessons
### why_backtest: Why test before you trade
- key points: An idea that has never been checked against history is a guess. Testing shows whether the rule has an edge, how often it loses, and how long losing streaks run. Most ideas fail, which saves money. Testing also builds the confidence needed to follow rules during a drawdown.
- common mistakes: Trading an idea from a video without checking it. Counting only the examples that worked.
- best example: crypto, BTCUSDT, 4h, a stretch of 100+ candles where a simple rule like "bullish engulfing at a prior swing low" can be counted.
- pattern_scanner: engulfing_bull
- on_screen_takeaway: Untested ideas are guesses. Testing tells you how an idea loses, which is what you need to know.

### define_rules: Writing rules you can test
- key points: A testable rule has an exact entry condition, an exact invalidation, and an exact exit. "Buy when it looks strong" cannot be tested. Define the timeframe, the markets, and the session. If two people would apply the rule differently, it is not a rule yet.
- common mistakes: Leaving discretion in the entry. Changing the rule halfway through the test.
- best example: forex, EURUSD, 1h, a pullback rule written out step by step and applied to several candles.
- pattern_scanner: swing_low
- on_screen_takeaway: If two people would apply your rule differently, it is not a rule yet.

### manual_backtest: Manual backtesting on the chart
- key points: Scroll the chart back, hide the future, and step forward one candle at a time. Record every instance the rule triggers, not just the good ones. Log entry, invalidation, outcome, and the reward-to-risk achieved. Fifty to a hundred samples is a reasonable minimum before drawing conclusions.
- common mistakes: Peeking at what happens next. Stopping after a few winning examples.
- best example: stock, SPY, 1d, replaying a year of candles and marking each trigger of a defined rule.
- pattern_scanner: engulfing_bull
- on_screen_takeaway: Step forward one candle at a time and record every trigger, including the ugly ones.

### sample_size_streaks: Sample size and losing streaks
- key points: A small sample can look great or terrible by luck. Even a decent rule produces long losing streaks; a 40% win rate can lose seven in a row without anything being wrong. Knowing the expected streak length in advance makes it survivable. Use the losing streak to check that risk per trade is small enough.
- common mistakes: Abandoning a rule after five losses. Trusting a rule after ten wins.
- best example: crypto, ETHUSDT, 4h, a sequence of several consecutive failed setups inside an otherwise normal period.
- pattern_scanner: engulfing_bear
- on_screen_takeaway: Losing streaks are normal. Know how long they can run before you start, and size for it.

### curve_fitting: Curve fitting and over-optimisation
- key points: Tweaking settings until past results look perfect produces a rule that fits noise. The more parameters, the easier it is to fit. Test a rule on one period and check it on a different period it has not seen. A rule that only works with one exact setting is suspicious.
- common mistakes: Optimising an indicator length to the best past result. Adding filters until every losing trade is excluded.
- best example: stock, NVDA, 1d, a moving average rule that looks great on one year and poor on the next.
- pattern_scanner: sma_cross
- on_screen_takeaway: A rule tuned to the past fits noise. Check it on data it has never seen.

### market_regimes: Regimes change
- key points: Rules behave differently in trends, ranges and high-volatility periods. A trend-following rule bleeds in a range; a mean-reversion rule gets run over in a trend. Test across different regimes and note where the rule struggles. Expecting one rule to work everywhere is unrealistic.
- common mistakes: Testing only on a bull market. Blaming the rule when the regime changed.
- best example: crypto, BTCUSDT, 1d, a period containing a strong trend followed by a long range, to contrast rule behaviour.
- pattern_scanner: range
- on_screen_takeaway: Every rule has a regime it struggles in. Find it in testing, not in a live account.

### journaling: The trading journal
- key points: A journal records the reason for each trade, the invalidation, the outcome and whether the rules were followed. Over time it reveals patterns in your own behaviour that no chart shows. Review it on a schedule, not only after a bad day. The journal is the backtest of the trader, not just the rule.
- common mistakes: Logging only profit and loss. Never reading old entries.
- best example: forex, XAUUSD, 4h, a recent setup walked through as if filling in a journal entry.
- pattern_scanner: pin_bar_bull
- on_screen_takeaway: The journal tests the trader. Log the reason, the invalidation and whether you followed the plan.
