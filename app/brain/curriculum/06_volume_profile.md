---
module: volume_profile
title: Volume profile: POC, value area and acceptance
level: intermediate
---

# Volume profile: POC, value area and acceptance

## Teaching voice
Volume profile turns time-based volume sideways: it shows at which prices the most business was done. Teach it as a map of agreement and disagreement, not a signal generator. Use clean examples where the point of control and the value area are obvious, and be upfront that profiles differ by data source and by the range you select.

## Lessons
### profile_basics: What a volume profile shows
- key points: A volume profile is a histogram of volume by price level over a chosen range. Fat areas are where buyers and sellers agreed; thin areas are where price moved fast with little trade. The shape depends entirely on the range you select. It is a description of the past session or range.
- common mistakes: Comparing profiles built from different ranges. Assuming the profile knows where price will go.
- best example: crypto, BTCUSDT, 1h, a two-day range where a clear high-volume node and a thin area are both visible.
- pattern_scanner: range
- on_screen_takeaway: Volume profile shows where trade happened, by price. Fat is agreement, thin is a fast move.

### point_of_control: The point of control
- key points: The POC is the single price with the most volume in the profile. It is the market's best idea of fair price for that range. Price often returns toward the POC when it drifts away without new information. A POC far from current price marks an area of old agreement that can act as a magnet or a barrier.
- common mistakes: Treating the POC as an exact level rather than a zone. Using the POC of a tiny range.
- best example: forex, EURUSD, 1h, a multi-day range where price repeatedly returns to the same high-volume price.
- pattern_scanner: support_level
- on_screen_takeaway: The POC is where the most business was done. Price tends to revisit old agreement.

### value_area: Value area high and low
- key points: The value area contains roughly 70% of the range's volume, bounded by VAH and VAL. Inside value, price rotates; outside value, price is either being accepted at new levels or rejected back. The edges are decision points. Nothing forces price to respect them.
- common mistakes: Fading every move outside value. Using value from one session on a totally different regime.
- best example: stock, SPY, 15m, a session where price leaves the prior value area, fails, and returns inside.
- pattern_scanner: range
- on_screen_takeaway: Inside value, price rotates. At the edges, the market decides between acceptance and rejection.

### acceptance_rejection: Acceptance versus rejection
- key points: Acceptance means price spends time and builds volume at a new level; rejection means it visits and leaves quickly, leaving a thin profile. A breakout that builds volume above the old VAH is being accepted. A breakout that prints thin volume and returns is rejected. Time at a price is the tell.
- common mistakes: Calling acceptance after two candles. Ignoring that news can create temporary acceptance.
- best example: crypto, ETHUSDT, 1h, a breakout above a prior value area that then builds several hours of volume above it.
- pattern_scanner: breakout_up
- on_screen_takeaway: Acceptance is time plus volume at a level. A quick visit and exit is rejection.

### low_volume_nodes: Low volume nodes and fast moves
- key points: Thin areas in the profile mark prices where few trades happened. Price tends to travel through them quickly because there is little resting interest. They are often the gaps between two high-volume areas. A thin zone above price is a path, not a promise.
- common mistakes: Expecting price to stop in a thin zone. Ignoring that thin zones can fill in over time.
- best example: crypto, SOLUSDT, 4h, a fast move through a thin profile area between two high-volume nodes.
- pattern_scanner: breakout_up
- on_screen_takeaway: Thin volume means little resting interest. Price moves through those zones fast in either direction.

### profile_with_structure: Combining profile with market structure
- key points: Profile levels gain meaning when they line up with swing highs, swing lows or old breakout points. A POC sitting at a prior swing low is a stronger zone than either alone. Use structure to pick which profile levels to care about. Confluence narrows attention; it does not remove risk.
- common mistakes: Drawing every profile level and drowning the chart. Trusting confluence enough to skip the invalidation.
- best example: crypto, BTCUSDT, 4h, a prior swing low that coincides with a high-volume node and holds on a retest.
- pattern_scanner: support_level
- on_screen_takeaway: Profile plus structure narrows the chart to a few zones that matter. Risk still has to be defined.
