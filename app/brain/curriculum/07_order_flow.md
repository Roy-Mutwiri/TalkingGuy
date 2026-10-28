---
module: order_flow
title: Order flow and liquidity
level: advanced
---

# Order flow and liquidity

## Teaching voice
Order flow is just the mechanics of how orders meet. Teach it plainly: there are market orders that take and limit orders that wait, and price moves to where the waiting orders are. Avoid the cult language around "smart money"; nobody on a chart can prove who placed an order. Show the footprints on real candles and keep the risk angle in every lesson.

## Lessons
### orders_basics: Market orders, limit orders and the book
- key points: Limit orders rest in the book and provide liquidity; market orders take it and move price. Price rises when buyers are willing to pay the ask faster than sellers refill it. Stop orders become market orders when triggered. Every candle is the result of this exchange.
- common mistakes: Thinking price moves because of "more buyers than sellers"; every trade has one of each. Confusing volume with aggression.
- best example: crypto, BTCUSDT, 15m, a sharp impulse candle to illustrate market orders eating through resting liquidity.
- pattern_scanner: volume_spike
- on_screen_takeaway: Price moves when market orders overwhelm resting limit orders. That is the whole mechanism.

### liquidity_pools: Where stop orders cluster
- key points: Stops tend to sit just beyond obvious swing highs and lows and round numbers. When price reaches them, the triggered stops become market orders and add fuel. This is why breakouts can spike and reverse. Knowing where stops likely sit helps you place yours less obviously.
- common mistakes: Assuming every level has a stop cluster. Moving your stop into the obvious spot.
- best example: forex, GBPUSD, 1h, a wick that runs just beyond a prior swing high then closes back below it.
- pattern_scanner: swing_high
- on_screen_takeaway: Stops cluster beyond obvious swings. Price often visits them before deciding.

### stop_hunts_sweeps: Sweeps and failed breakouts
- key points: A sweep is a move beyond a swing level that triggers stops and then reverses. It appears as a long wick beyond the level with a close back inside. It shows that the liquidity was taken and the follow-through was absent. The invalidation is a close beyond the sweep extreme.
- common mistakes: Calling every wick a sweep. Fading a sweep in a trend without a reclaim.
- best example: crypto, ETHUSDT, 4h, a wick below a prior swing low followed by a close back above within 1-2 candles.
- pattern_scanner: pin_bar_bull
- on_screen_takeaway: A sweep takes the stops and fails to continue. The close back inside is the information.

### absorption: Absorption at a level
- key points: Absorption is heavy volume at a level with little price movement, meaning resting orders are soaking up aggression. It often shows as repeated tests with shrinking progress. When absorption ends, price can move sharply the other way. It is visible as effort without result.
- common mistakes: Mistaking a slow grind for absorption. Expecting absorption to hold forever.
- best example: stock, NVDA, 15m, several high-volume tests of the same low with small candle bodies.
- pattern_scanner: volume_spike
- on_screen_takeaway: Absorption is big volume with no progress. Someone is taking the other side.

### imbalance_gaps: Imbalances and fair value gaps
- key points: An imbalance is a fast move that leaves little two-way trade, visible as a gap between the wicks of candles one and three. Price sometimes returns to these areas because business was skipped there. It is a tendency, not a law, and many gaps never fill. Treat a gap as a zone of interest to combine with structure.
- common mistakes: Trading every gap on every timeframe. Expecting gaps to fill on a schedule.
- best example: crypto, SOLUSDT, 1h, a three-candle impulse leaving a clear gap, later partly revisited.
- pattern_scanner: breakout_up
- on_screen_takeaway: Imbalances mark skipped business. Some get revisited, many do not, so combine them with structure.

### footprint_delta: Delta and footprint basics
- key points: Delta is market buy volume minus market sell volume per candle. Positive delta with rising price is normal; positive delta with price falling shows buying being absorbed. Footprint charts show this per price level inside each candle. These tools need exchange-level data and are easy to over-read.
- common mistakes: Acting on a single candle's delta. Comparing delta across venues with different data.
- best example: crypto, BTCUSDT, 15m, a candle with strong buy volume and a small or negative price result near a swing high.
- pattern_scanner: volume_spike
- on_screen_takeaway: Delta shows who was aggressive. Price shows whether it worked.

### order_flow_risk: Order flow does not remove risk
- key points: Reading liquidity improves context, not certainty. The invalidation is still a price level, usually beyond the sweep or absorption area. Position size still comes from the distance to that level. Order flow is one more lens, judged by the same rules as any other.
- common mistakes: Believing liquidity concepts make losses avoidable. Sizing up because a setup "looks institutional".
- best example: forex, XAUUSD, 1h, a sweep setup that works and a similar one that fails, side by side.
- pattern_scanner: pin_bar_bear
- on_screen_takeaway: Order flow adds context. Risk is still defined by a level and a position size.
