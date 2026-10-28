---
module: risk_management
title: Risk management and position sizing
level: beginner
---

# Risk management and position sizing

## Teaching voice
This is the module that keeps people in the game, so teach it with real numbers and a calm voice. Every example should state the invalidation level, the distance to it, and the position size that follows. Never mention expected profits or returns; talk about losses that are survivable. Risk management is the only part of trading fully under your control.

## Lessons
### risk_per_trade: Risk per trade in percent
- key points: Decide the maximum loss per idea as a percentage of the account, commonly a small single-digit figure. Ten losses in a row at that size should still leave the account intact. The percentage is fixed before looking at the chart. Consistency matters more than the exact number.
- common mistakes: Risking more because a setup "looks certain". Changing risk size after a loss.
- best example: crypto, BTCUSDT, 4h, a setup with a clearly marked invalidation to illustrate fixed-percent risk.
- pattern_scanner: engulfing_bull
- on_screen_takeaway: Fix the maximum loss per idea first. Everything else is built on that number.

### position_sizing: Position size from the invalidation
- key points: Position size equals risk amount divided by the distance from entry to invalidation. A wide stop means a smaller position; a tight stop means a larger one. Size is an output of the chart, never an input. Fees and slippage widen the real distance.
- common mistakes: Picking a size first and then placing the stop where the size allows. Forgetting leverage multiplies the move, not the risk formula.
- best example: forex, EURUSD, 1h, a pullback entry with the invalidation below a swing low, showing the distance in pips.
- pattern_scanner: swing_low
- on_screen_takeaway: Size comes from the distance to invalidation. Wide stop, small size; tight stop, larger size.

### invalidation_levels: Choosing the invalidation
- key points: The invalidation is the price where the idea is proven wrong, usually beyond the swing that justified the entry. It is a logical level, not a dollar amount you are comfortable losing. Placing it where stops obviously cluster invites being swept. Decide it before entry and do not move it further away.
- common mistakes: Setting the stop at a round dollar loss. Widening the stop while in the trade.
- best example: crypto, ETHUSDT, 4h, an engulfing candle at support with the invalidation just below the candle low.
- pattern_scanner: engulfing_bull
- on_screen_takeaway: Invalidation is where the idea is wrong, not where the loss feels big.

### reward_to_risk: Reward-to-risk and win rate
- key points: Reward-to-risk compares the distance to a logical target with the distance to invalidation. A strategy with low win rate can survive with large reward-to-risk, and vice versa. Both numbers together determine whether an approach can hold up. Neither alone says anything.
- common mistakes: Chasing high win rate with huge stops. Demanding 3:1 on every trade regardless of structure.
- best example: stock, AAPL, 1d, a pullback entry with a prior swing high as the logical target and a swing low as invalidation.
- pattern_scanner: higher_highs
- on_screen_takeaway: Win rate and reward-to-risk only mean something together.

### drawdown_math: Why drawdowns are asymmetric
- key points: A 20% loss needs a 25% gain to recover; a 50% loss needs 100%. Losses compound against you faster than gains compound for you. Small consistent risk keeps drawdowns shallow and recoverable. This is the mathematical reason for the risk-per-trade rule.
- common mistakes: Doubling size to "make it back". Measuring drawdown in dollars instead of percent.
- best example: crypto, SOLUSDT, 1d, a sharp decline and the much larger rally required to return to the prior high.
- pattern_scanner: lower_lows
- on_screen_takeaway: Losses are asymmetric. Keeping them small is the whole game.

### correlation_risk: Correlated positions
- key points: Several positions in correlated assets behave like one large position. Long BTC, ETH and SOL at the same time is mostly one bet on crypto. Total open risk should be capped across correlated ideas. Diversification across highly correlated charts is an illusion.
- common mistakes: Counting each position's risk separately. Taking the same setup on five pairs.
- best example: crypto, BTCUSDT, 4h, shown alongside ETHUSDT and SOLUSDT moving in near lockstep.
- pattern_scanner: none
- on_screen_takeaway: Correlated positions are one position. Cap total risk across them.

### leverage_reality: Leverage without illusions
- key points: Leverage changes the margin required, not the correct position size. Size still comes from risk divided by stop distance. High leverage mainly reduces the distance to liquidation. Liquidation price should always be far beyond the invalidation.
- common mistakes: Using the maximum leverage offered. Letting liquidation act as the stop loss.
- best example: crypto, BTCUSDT, 1h, a volatile stretch illustrating how a liquidation level close to price gets hit by ordinary noise.
- pattern_scanner: volume_spike
- on_screen_takeaway: Leverage changes margin, not risk. Position size still comes from the stop distance.
