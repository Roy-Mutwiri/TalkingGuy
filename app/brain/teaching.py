"""Teaching flow for Haddan: the lesson arc, signposts, and a library of plain-words definitions,
analogies, chart stories, mistakes and check questions for the concepts in the curriculum.

See teaching.md for where this comes from (Rosenshine, Feynman, Mind Math Money, Al Brooks, Adam Khoo,
Rayner Teo, Mark Douglas, Wyckoff, Brian Shannon, signposting research).
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

DOCTRINE_PATH = Path(__file__).resolve().parent / "teaching.md"
DRAWING_PATH = Path(__file__).resolve().parent / "drawing.md"


def doctrine() -> str:
    try:
        return DOCTRINE_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def drawing_doctrine() -> str:
    """The chartist's doctrine: what every chart action is for, how to anchor it, when it is invalidated."""
    try:
        return DRAWING_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


@dataclass
class Notes:
    plain: str          # the idea in one plain sentence
    analogy: str        # a picture the listener already owns
    story: str          # who was in control / trapped, what the market did
    confirm: str        # what makes it real
    mistake: str        # the beginner misread, contrasted with the right read
    check: str          # one answerable question for the chat
    hint: str = ""      # the hint during the answer window


# keyword -> notes. First matching key (by title, then body) wins; "default" is the fallback.
LIBRARY: dict[str, Notes] = {
    "wick": Notes(
        "A wick is the part of the candle where price went but could not stay.",
        "Think of price knocking on a door. The wick is how far it got in before someone pushed it back out.",
        "Buyers pushed price up into the wick, sellers met them there, and the close tells you who won the argument.",
        "A long wick means something only when it prints at a level that mattered before, and the next candle respects it.",
        "Beginners call every wick a rejection. A wick in the middle of nowhere is just noise; a wick at a prior high or low is information.",
        "Does a long wick matter more at a level, or in the middle of a range? Type L or M.", "Hint: where did price react before?"),
    "engulfing": Notes(
        "An engulfing candle is one candle whose body swallows the whole body of the candle before it.",
        "It's like a tug of war where one side suddenly yanks the rope past the other team's starting line.",
        "The first candle shows one side winning. The second shows the other side absorbing all of that and pushing beyond it. Anyone who joined the first candle late is now trapped.",
        "It counts when it prints at a level and the next candle does not immediately undo it.",
        "Beginners trade every engulfing candle they see. The pattern is the same everywhere; the location is what changes the odds.",
        "Which matters more: the size of the engulfing candle, or where it printed? Type S or W.", "Hint: context first, pattern second."),
    "doji": Notes(
        "A doji is a candle that opens and closes at almost the same price: nobody won that block of time.",
        "It's a pause in a conversation. A pause means something only depending on what was said before it.",
        "After a long run one way, a doji says the pushing side ran out of breath. Inside a quiet range it says nothing at all.",
        "The candle after the doji is the decision. The doji itself is only the question.",
        "Beginners treat a doji as a reversal signal. It's a hesitation. Wait for the next candle to say who won.",
        "Is a doji a decision or a pause? Type D or P.", "Hint: who won that candle? Nobody."),
    "inside bar": Notes(
        "An inside bar sits completely inside the range of the candle before it.",
        "It's a coiled spring. Compression now, expansion later. Which way the spring goes is not written on the spring.",
        "Neither side is willing to push past the mother candle's extremes, so orders build up on both sides of it.",
        "The break of the mother candle's high or low is the event. Until then it's just waiting.",
        "Beginners guess the direction of the break. The honest move is to let the break tell you.",
        "Can you know which way an inside bar will break before it breaks? Type Y or N.", "Hint: compression says when, not where."),
    "support": Notes(
        "Support is a price area where buyers showed up before and price turned up.",
        "It's a floor that held weight before. You trust a floor more each time it holds, and you stop trusting it the moment it cracks.",
        "Sellers pushed price down to the area, buyers who remembered it stepped in, and sellers who sold the low are now the ones chasing.",
        "Support is confirmed by a reaction: a wick, a close back above, a second touch that holds.",
        "Beginners draw a line and treat it as a wall. It's a zone, and it only matters if price reacts there again.",
        "Is support a line or a zone? Type L or Z.", "Hint: look how many candles touched it."),
    "resistance": Notes(
        "Resistance is a price area where sellers showed up before and price turned down.",
        "It's a ceiling. Price keeps bumping its head there until one day it doesn't, and that day is the lesson.",
        "Buyers pushed into the area, sellers who remembered it unloaded, and late buyers got trapped above the close.",
        "Confirmed by rejection: upper wicks, closes back below, repeated touches that fail.",
        "Beginners short the first touch of every ceiling. The third touch with shrinking pullbacks is a very different story from the first.",
        "On the third touch of resistance, is the ceiling stronger or weaker? Type S or W.", "Hint: how deep were the pullbacks between touches?"),
    "structure": Notes(
        "Market structure is the pattern of highs and lows: higher highs and higher lows going up, lower highs and lower lows going down.",
        "It's footprints in snow. You don't need to see the person to know which way they're walking.",
        "Each higher low is buyers stepping in earlier than last time. The first lower low after a run of higher lows is the moment that changes.",
        "Structure is confirmed by a close beyond the last swing, not a wick through it.",
        "Beginners mark every tiny bump as a swing. A swing high needs lower highs on both sides of it.",
        "In an uptrend, which breaks first: a higher low or a higher high? Type L or H.", "Hint: who is stepping in earlier each time?"),
    "break of structure": Notes(
        "A break of structure is a close beyond the last swing high or low that was holding the trend.",
        "It's the first time the person walking in the snow turns around. One step back is not a turn; a new direction is.",
        "Everyone who bought the last higher low expected it to hold. When it breaks, those positions are under water and their stops add fuel.",
        "Confirmed by a close beyond the swing and a failure to reclaim it on the retest.",
        "Beginners call a wick through a swing a break. A wick is a visit; a close is a decision.",
        "Does a wick through a swing low count as a break of structure? Type Y or N.", "Hint: where did the candle close?"),
    "liquidity": Notes(
        "Liquidity is where lots of orders sit, usually stops just above obvious highs and below obvious lows.",
        "Think of a crowded doorway. Big players need a crowd to trade against, and the crowd stands where the stops are.",
        "Price runs the obvious high, stops get hit, late buyers chase, and then price reverses: the crowd provided the exit.",
        "A liquidity sweep is confirmed when price pokes through the level and closes back inside it.",
        "Beginners place stops exactly at the obvious low with everyone else. That's the doorway.",
        "Where do most stop losses sit: above obvious highs, or in the middle of a range? Type A or M.", "Hint: where would you put yours?"),
    "order block": Notes(
        "An order block is the last candle before a strong move, where big orders were placed.",
        "It's the footprint left by someone heavy. When price comes back to the footprint, it tends to react.",
        "The last opposite candle before the displacement is where institutions filled; when price returns, leftover orders defend it.",
        "Confirmed by displacement after it and a reaction when price returns the first time.",
        "Beginners mark every candle before every move. Without displacement, it's just a candle.",
        "Which part makes an order block real: the candle, or the strong move after it? Type C or M.", "Hint: no displacement, no block."),
    "fair value gap": Notes(
        "A fair value gap is a three-candle gap where price moved so fast it left a hole.",
        "It's a staircase with a missing step. Markets often come back to fill the step before continuing.",
        "One side pushed so hard nobody traded in between. Those untraded prices tend to get revisited.",
        "Confirmed by price returning into the gap and continuing in the original direction.",
        "Beginners expect every gap to fill. Many do; the ones in strong trends often don't, and that's information too.",
        "Does every fair value gap get filled? Type Y or N.", "Hint: strong trends leave holes behind."),
    "trend": Notes(
        "A trend is price making progress in one direction with pullbacks that don't undo it.",
        "A trend is a river. You can swim against it, but why would you?",
        "In an uptrend, pullbacks are buyers waiting for a discount; each higher low is them stepping in sooner.",
        "A trend is confirmed by structure, not by feeling: higher highs and higher lows, or the opposite.",
        "Beginners decide the trend from the last three candles. Zoom out one timeframe and look again.",
        "Does a trend get defined by the last three candles, or by the highs and lows? Type C or H.", "Hint: zoom out."),
    "pullback": Notes(
        "A pullback is price moving against the trend for a while without breaking the structure.",
        "It's the river bending. Still the same river, still the same direction.",
        "Profit-taking pushes price back; buyers who missed the move use it to get in; the higher low is where they win the argument.",
        "Confirmed when the pullback holds above the last higher low and price resumes.",
        "Beginners sell every pullback thinking the trend ended. It ends when structure breaks, not when a red candle appears.",
        "Does a red candle in an uptrend mean the trend ended? Type Y or N.", "Hint: did the last higher low hold?"),
    "range": Notes(
        "A range is price bouncing between a floor and a ceiling with no progress either way.",
        "It's a ball in a hallway: wall, wall, wall. Boring until the ball goes through a wall.",
        "Buyers defend the floor, sellers defend the ceiling, and the middle is where nobody has an edge.",
        "A range is confirmed by at least two touches of each side.",
        "Beginners trade the middle of the range. The edges are where decisions happen; the middle is noise.",
        "Where is the worst place to make a decision in a range? Type E for edge or M for middle.", "Hint: where does nobody have an edge?"),
    "breakout": Notes(
        "A breakout is price closing beyond a level that held before.",
        "It's a crowd finally pushing through a door that was stuck. Sometimes the door swings back.",
        "Buyers overwhelm the sellers at the ceiling; sellers who were short are forced to cover and add fuel.",
        "Confirmed by a close beyond the level and a retest that holds.",
        "Beginners buy the first poke above the level. Half of those are the market testing who's paying attention.",
        "Which confirms a breakout: a wick above the level, or a close above it? Type W or C.", "Hint: the close is the decision."),
    "false breakout": Notes(
        "A false breakout is price pushing through a level and then closing back inside.",
        "It's a fake-out in football. The defender bites, and the play goes the other way.",
        "Breakout buyers jump in above the level, no follow-through comes, their stops below it become the fuel for the reversal.",
        "Confirmed by the close back inside the level and a move away from it.",
        "Beginners see a false breakout as bad luck. It's one of the most repeatable stories on any chart.",
        "After a false breakout above a range, where are the trapped traders? Type A for above or B for below.", "Hint: who bought the breakout?"),
    "volume": Notes(
        "Volume is how much got traded in a candle: the amount of agreement behind a move.",
        "Volume is the crowd noise. A goal with a silent stadium is suspicious.",
        "A move on rising volume has participants behind it; a move on fading volume is running out of people.",
        "Confirmed when volume expands in the direction of the trend and dries up on pullbacks.",
        "Beginners read volume alone. Volume only means something next to the price move it came with.",
        "A breakout on tiny volume: trust it more or less? Type M or L.", "Hint: where's the crowd?"),
    "point of control": Notes(
        "The point of control is the price where the most business was done over a period.",
        "It's the busiest table in the restaurant. Price tends to come back to where everyone agreed.",
        "The market spent its time there because buyers and sellers agreed; moves away from it either get accepted or get pulled back.",
        "Confirmed by price reacting on the first return to it.",
        "Beginners treat the point of control as a target. It's a magnet and a reference, not a promise.",
        "Does price usually revisit the point of control, or avoid it? Type R or A.", "Hint: where was the agreement?"),
    "value area": Notes(
        "The value area is where most of the trading happened: the fair zone.",
        "It's the comfort zone. Outside it, one side is uncomfortable and reacts.",
        "Price above value means buyers have to prove it's accepted; failing that, it rotates back in.",
        "Acceptance outside value is confirmed by closes and time spent there, not one poke.",
        "Beginners chase price outside value. The question is whether it gets accepted or rejected there.",
        "Outside the value area, what matters more: the poke or the acceptance? Type P or A.", "Hint: time and closes."),
    "vwap": Notes(
        "VWAP is the average price weighted by volume: what the average participant actually paid.",
        "It's the class average. Above it the buyers are happy; below it they're nervous.",
        "When price holds above VWAP, buyers are in profit and defend it; when it loses VWAP, they become sellers.",
        "Confirmed by price respecting it as support or resistance on the retest.",
        "Beginners use VWAP as a buy signal. It's a reference for who's winning, not a trigger.",
        "If price is below VWAP, who is uncomfortable: buyers or sellers? Type B or S.", "Hint: who paid more than it's worth now?"),
    "moving average": Notes(
        "A moving average is the average close over the last N candles, drawn as a line.",
        "It's a smoothed-out shadow of price. It follows; it never leads.",
        "In a trend, price stretches away from the average and comes back to it; the average tells you the mood, not the next move.",
        "Confirmed as useful when price reacts around it repeatedly in the trend direction.",
        "Beginners trade the crossover. By the time averages cross, the move that caused it already happened.",
        "Does a moving average lead price or follow it? Type L or F.", "Hint: it's an average of the past."),
    "rsi": Notes(
        "RSI measures how fast price moved recently, from zero to a hundred.",
        "It's a speedometer, not a brake. Fast doesn't mean about to stop.",
        "High RSI in a strong trend means strength, not reversal; the reversal clue is divergence: price makes a new high and RSI doesn't.",
        "Confirmed when divergence shows up at a level and price structure breaks after it.",
        "Beginners sell because RSI is above seventy. Strong trends live above seventy for weeks.",
        "RSI at eighty in a strong uptrend: sell signal or strength? Type S or T.", "Hint: speedometer."),
    "macd": Notes(
        "MACD is the gap between two moving averages, plus a signal line that smooths it.",
        "It's momentum's momentum: is the gap between fast and slow getting bigger or smaller?",
        "A shrinking histogram says the push is losing steam even while price still rises; that's where divergences come from.",
        "Confirmed when the momentum change lines up with a level and a structure break.",
        "Beginners trade every MACD cross. It's a derivative of a derivative; use it to read momentum, not to pull triggers.",
        "Is MACD faster or slower than price? Type F or S.", "Hint: it's built from averages."),
    "divergence": Notes(
        "Divergence is price making a new extreme while an indicator doesn't.",
        "It's the engine revving less each time the car goes faster. Something is fading.",
        "Price squeezes out a new high, but the push behind it is weaker; the buyers who chased that high are the first to get trapped.",
        "Confirmed only when structure breaks after it; divergence alone can last a long time.",
        "Beginners trade divergence on its own. Divergence says momentum is fading; structure says when it matters.",
        "Can divergence last a long time before anything happens? Type Y or N.", "Hint: fading isn't stopping."),
    "fibonacci": Notes(
        "Fibonacci levels split a move into fractions traders watch for pullbacks, like the halfway point.",
        "They're the mile markers on a road. Useful because everybody uses the same markers.",
        "A pullback into the fifty to sixty-one percent area is where trend buyers tend to show up, because they're all looking at the same map.",
        "Confirmed when the level lines up with structure: a prior low, a zone, a gap.",
        "Beginners draw fibs everywhere. A fib alone is a coincidence; a fib on a zone is confluence.",
        "A fib level on its own, or a fib level on a prior low: which is stronger? Type A or L.", "Hint: confluence."),
    "stop loss": Notes(
        "A stop loss is the price where you admit the idea was wrong and get out.",
        "It's the smoke alarm, not the fire. You don't argue with it; you leave.",
        "The stop goes where the idea breaks: beyond the level that gave you the reason. Anywhere else is a guess.",
        "A good stop is confirmed by logic, not by comfort: through this price, the story is over.",
        "Beginners place stops at a round number or a dollar amount they can stand. The chart doesn't care what you can stand.",
        "Should a stop be placed where the idea breaks, or where the loss feels okay? Type B or F.", "Hint: invalidation."),
    "position sizing": Notes(
        "Position sizing is choosing how much to trade so that a loss is small enough not to matter.",
        "It's the seatbelt. It doesn't make you drive better; it makes crashes survivable.",
        "Size comes from the distance to your invalidation and the amount you're willing to lose, never from confidence.",
        "Confirmed when a full loss is boring: one percent, maybe less.",
        "Beginners size by feeling. Size by distance: wider stop, smaller size.",
        "Wider stop means bigger or smaller position? Type B or S.", "Hint: risk stays fixed."),
    "risk reward": Notes(
        "Risk to reward is how much you can lose against how much you can reasonably gain on an idea.",
        "It's the price of a lottery ticket against the prize. Cheap tickets with real prizes are the only ones worth buying.",
        "You can be wrong more than half the time and still come out ahead, if the wins are bigger than the losses.",
        "Confirmed by the chart, not the wish: the target has to be a level price actually reaches.",
        "Beginners force a three-to-one by drawing targets in the sky. The chart decides the reward, you decide the risk.",
        "Can you be right only forty percent of the time and still make progress? Type Y or N.", "Hint: size of wins versus losses."),
    "psychology": Notes(
        "Trading psychology is managing the part of you that wants certainty in a game that has none.",
        "It's a casino from the house side. The house doesn't know the next hand; it knows the edge over a thousand hands.",
        "Fear of missing out buys the top; revenge trading sells the bottom; both come from needing this one trade to matter.",
        "A calm trader is confirmed by boring losses: they happen, they're small, nothing changes.",
        "Beginners think the market made them angry. The market is neutral; the anger came from the expectation.",
        "Does the market owe you a win after three losses? Type Y or N.", "Hint: every trade is unique."),
    "fomo": Notes(
        "FOMO is the urge to jump in because price is moving without you.",
        "It's running after a bus that already left. There's always another bus.",
        "Late chasers buy from the people who were early; they are the liquidity for the exit.",
        "The cure is confirmed by a rule: no plan before the move, no trade during it.",
        "Beginners think a missed move is a loss. A missed move costs nothing; a chased one does.",
        "Does missing a move cost you money? Type Y or N.", "Hint: check your account."),
    "backtest": Notes(
        "Backtesting is checking an idea against the past before you trust it with money.",
        "It's a driving test before the road. You still don't know the traffic, but you know you can drive.",
        "A rule that worked on two charts is a story; a rule that worked on two hundred is a tendency.",
        "Confirmed by enough samples, honest losses counted, and the same rules every time.",
        "Beginners backtest with hindsight: they see the result before they mark the entry. Hide the future first.",
        "Is a setup that worked three times proven? Type Y or N.", "Hint: sample size."),
    "wyckoff": Notes(
        "Wyckoff is reading a sideways range as a story of big players quietly buying or selling.",
        "It's a warehouse. Someone fills it while the price looks boring, then the price finds out.",
        "Selling climax, rally, test, a spring under the lows that grabs stops, then the markup: cause builds, effect follows.",
        "Confirmed by the spring holding and price pressing the top of the range with strength.",
        "Beginners want the schematic to match perfectly. Ranges rhyme; they don't copy.",
        "In a spring, who gets trapped: breakout sellers or buyers? Type S or B.", "Hint: who sold the new low?"),
    "absorption": Notes(
        "Absorption is when heavy selling hits a level and price refuses to drop.",
        "It's pushing a door that someone is holding from the other side.",
        "Sellers keep hitting the bid and a passive buyer keeps taking everything; when sellers run out, price has only one way to go.",
        "Confirmed by high volume with little price progress, then a move away from the level.",
        "Beginners see big red volume and expect a drop. If price didn't drop on it, ask who was buying.",
        "Heavy selling and price doesn't fall: who's winning? Type B or S.", "Hint: who's holding the door?"),
    "delta": Notes(
        "Delta is buying volume minus selling volume: who was more aggressive.",
        "It's the score of who shouted louder, not who got their way.",
        "Aggressive buyers can push and still fail if passive sellers absorb them; delta shows the push, price shows the result.",
        "Confirmed when delta and price agree at a level; when they disagree, somebody is about to be wrong.",
        "Beginners trade delta alone. Delta shows who was aggressive; price shows whether it worked.",
        "Positive delta and price going down: who's winning? Type B or S.", "Hint: aggression isn't control."),
    "candle": Notes(
        "A candle is one block of time summarised as four prices: open, high, low, close.",
        "It's a round in a boxing match. Where they started, how far each side pushed, who was standing at the bell.",
        "The body is the result, the wicks are the fight. A long body with small wicks means one side ran the round.",
        "Read candles in context: the same candle at a level and in the middle of nowhere are different stories.",
        "Beginners read colour only. The close relative to the range and the location say far more.",
        "Which tells you more: the candle's colour, or where it closed in its range? Type C or R.", "Hint: who was standing at the bell?"),
    "drawdown": Notes(
        "A drawdown is how far your account fell from its peak, and it hurts more than it looks because you need a bigger gain to get back.",
        "Lose half, and you need to double just to get home. The hole is always deeper than the fall.",
        "Each loss makes the next one proportionally bigger; traders in a drawdown size up to recover, and that is how a dip becomes a crater.",
        "Survival is confirmed by small, fixed risk per idea: a ten percent drawdown needs eleven percent back, a fifty percent one needs a hundred.",
        "Beginners think a fifty percent loss needs a fifty percent gain to recover. It needs a hundred.",
        "Lose fifty percent, how much do you need to make back: fifty or a hundred percent? Type 50 or 100.", "Hint: half of what's left is less."),
    "channel": Notes(
        "A channel is two parallel lines: the trendline through the swings on one side, and a copy of it on the other side.",
        "It's a hallway. Price walks between the walls, bounces, and the exit is the only moment that matters.",
        "Buyers defend the lower wall, sellers the upper one; each touch that holds adds confidence, and the first close outside is the crowd changing its mind.",
        "A channel is real after two touches on each wall. The third touch is the test.",
        "Beginners draw the parallel through the single highest wick. Draw it through the swing that was respected, and let the odd wick poke out.",
        "Does a wick outside the channel break it, or does a close? Type W or C.", "Hint: visits versus decisions."),
    "regression": Notes(
        "A regression channel is the average path of price over a range, with bands a set number of standard deviations away.",
        "It's the lane markings on a road: the middle line is where the car has averaged, the bands are how far it usually drifts.",
        "When price reaches a band it is stretched from its own average; it usually comes back toward the middle, but a trend can ride a band for a long time.",
        "Only meaningful for the range you selected. Change the range and the channel changes.",
        "Beginners fade every touch of the outer band. In a strong trend the band is where price lives.",
        "If you change the start of the range, does the channel stay the same? Type Y or N.", "Hint: it's computed from the bars you chose."),
    "pitchfork": Notes(
        "A pitchfork is a median line from a pivot through the middle of the next two swings, with two parallel tines.",
        "Think of a rake dragged through the sand: the middle tooth is the path, the outer teeth are the edges of the groove.",
        "The median line is the expected centre of the move; price tends to return to it after each tine touch, until it doesn't.",
        "It counts when price has respected the median at least once after you drew it.",
        "Beginners pick three random points. The pivots must be the actual swing high and lows that started the move.",
        "Where should price spend most of its time inside a pitchfork? Type M for median or T for tines.", "Hint: the centre of the groove."),
    "fibonacci extension": Notes(
        "A Fibonacci extension projects the size of the last impulse from the end of the pullback.",
        "It's a ruler you lay down at the end of a rest to see how far a move of the same size would reach.",
        "Traders who caught the impulse take profit around the one-to-one and one point six one eight projections, so reactions cluster there.",
        "Useful only when the extension lands on a level that already mattered.",
        "Beginners read the extension as a target. It's a ruler for scale; the market owes it nothing.",
        "Is a one point six one eight extension a target or a reference? Type T or R.", "Hint: rulers don't promise."),
    "position": Notes(
        "The position tool draws the entry, the stop and the target as a red box and a green box, with the ratio between them.",
        "It's a before-you-cross-the-street check: how far is the car, how far is the curb.",
        "The red box is what someone risks if the idea is wrong; the green box is what they'd make if it's right. Size comes from the red box, never the other way round.",
        "The stop sits beyond the invalidation of the idea, and the target sits at a real level, not a round number.",
        "Beginners move the stop to make the ratio look good. The ratio is an output; move the stop and you changed the idea.",
        "Which box decides position size, the red one or the green one? Type R or G.", "Hint: risk first."),
    "measure": Notes(
        "The measure tool shows how far and how fast price moved between two points: price change, percent, bars and time.",
        "It's a tape measure. You don't guess the size of a room, you measure it.",
        "Measuring the last leg tells you whether the current one is normal or exceptional, and how long rests usually take.",
        "It is pure description; nothing to confirm.",
        "Beginners describe moves as huge or tiny. Say the number.",
        "Is a two percent move big or small on this chart? Type B or S.", "Hint: measure the last three legs first."),
    "volume profile": Notes(
        "A volume profile turns volume sideways: it shows how much was traded at each price over a chosen range.",
        "It's a map of where the crowd stood. Fat areas are where people agreed; thin areas are where everyone ran through.",
        "The point of control is the fairest price of that range; price drifts away from it and tends to come back unless something new happened.",
        "Only as good as the range you chose. Change the range, the profile changes.",
        "Beginners compare profiles of different ranges. Say the range every time.",
        "Does price move faster through fat areas or thin areas? Type F or T.", "Hint: where did nobody trade?"),
    "anchored vwap": Notes(
        "An anchored VWAP is the average price everyone paid since one chosen bar, weighted by volume.",
        "It's the average ticket price since the doors opened. Above it, the crowd that came in is up; below it, they're under water.",
        "Anchor it on the swing that started the move: when price returns to the line, the people who bought the move decide whether to defend it.",
        "It is meaningful when the anchor is a bar that mattered: a swing, a session open, a news candle.",
        "Beginners anchor anywhere. The anchor is the whole point.",
        "Where should an anchored VWAP start, at a random bar or at the turn? Type R or T.", "Hint: the doors opened at the turn."),
    "bollinger": Notes(
        "Bollinger bands are a moving average with bands a set number of standard deviations above and below.",
        "They're a rubber band around price: tight when it's calm, wide when it's wild.",
        "Tight bands are the market holding its breath; the expansion that follows is the move, and the first direction is often tested.",
        "A close outside a band means price is stretched, not that it is reversing.",
        "Beginners sell every touch of the upper band. In a trend price walks the band.",
        "Do tight bands tell you the direction of the next move? Type Y or N.", "Hint: compression says when, not where."),
    "rsi": Notes(
        "RSI measures the speed of recent gains against recent losses on a scale from zero to a hundred.",
        "It's a speedometer, not a map. It tells you how fast, not where you're going.",
        "Above seventy means the move has been fast, which in a trend is normal. The useful read is divergence: price makes a new high and RSI doesn't.",
        "Divergence counts when it prints at a level and price confirms with a lower high afterwards.",
        "Beginners short at seventy. Strong trends sit above seventy for weeks.",
        "Does RSI above seventy mean sell? Type Y or N.", "Hint: fast is not finished."),
    "macd": Notes(
        "MACD is the gap between a fast and a slow moving average, with a signal line and a histogram of the difference.",
        "It's the gap between two runners: when the fast one pulls away the gap grows, when it tires the gap closes.",
        "The histogram shrinking while price still rises is momentum fading; the cross is the late confirmation.",
        "Read it with structure: a cross with no change in highs and lows is noise.",
        "Beginners trade every cross. Half of them happen in the middle of nothing.",
        "Is the MACD cross early or late compared to the histogram? Type E or L.", "Hint: the gap changes before the lines cross."),
    "session": Notes(
        "A session is the stretch of the day when a particular region's banks and funds are at their desks.",
        "It's shift change at a factory. The night shift leaves marks the day shift reads first.",
        "The previous session's high and low are where stops cluster, so the next session often sweeps one of them before it chooses a direction.",
        "A sweep counts when price pokes through the session extreme and closes back inside.",
        "Beginners ignore the clock. The same candle means different things at the London open and at lunch in New York.",
        "Which gets swept first more often, the previous session high or low? Type H, L, or N for no rule.", "Hint: there is no rule; there is a map."),
    "key levels": Notes(
        "Key levels are the previous day and week high and low, and the day and week open.",
        "They're the landmarks every driver in town knows. Reactions cluster there because everyone is looking at them.",
        "Price above the previous day high with acceptance is a different day from price failing there and closing back under.",
        "A level is respected when price reacts to it, not when it is merely drawn.",
        "Beginners draw twenty levels. Draw the ones every desk watches, then watch the reaction.",
        "Does drawing a level make it matter? Type Y or N.", "Hint: the reaction makes it matter."),
    "alert": Notes(
        "An alert is a line that tells you the moment price touches it, so you don't stare at the screen.",
        "It's a doorbell. It tells you someone is at the door, not who it is.",
        "When an alert fires the job starts: watch how the candle closes against the level.",
        "A touch is a touch; a close is a decision.",
        "Beginners act on the ring. Look through the peephole first.",
        "Is an alert a signal or a reminder? Type S or R.", "Hint: it rings, it doesn't decide."),
    "head and shoulders": Notes(
        "A head and shoulders is three peaks, the middle one highest, with a neckline through the two dips.",
        "It's a crowd that cheered twice and then couldn't cheer a third time as loud.",
        "Buyers who bought the head are trapped above; the right shoulder is their failed rescue; the neckline break is their exit.",
        "Confirmed only by a close below the neckline; the retest of the neckline from below is the second chance.",
        "Beginners call it before the right shoulder exists. Three peaks or it isn't one.",
        "Is a head and shoulders confirmed at the right shoulder or at the neckline close? Type S or N.", "Hint: the exit, not the shape."),
    "double top": Notes(
        "A double top is two highs at about the same price with a dip between them.",
        "It's knocking on the same door twice and being turned away twice.",
        "The second high traps the late buyers; the close below the middle dip is where they give up.",
        "Confirmed by a close below the neckline, invalidated by a close above the two highs.",
        "Beginners trade every pair of equal highs. Equal highs are also where breakouts start; wait for the close.",
        "Does a double top need a close below the neckline to count? Type Y or N.", "Hint: shapes versus patterns."),
    "triangle": Notes(
        "A triangle is highs and lows squeezing toward each other, a range that is getting narrower.",
        "It's a spring being compressed. Energy builds, the release direction is not written on the spring.",
        "Each side gives ground; the break shows which side ran out of patience first, and the failed side's stops fuel it.",
        "Confirmed by a close outside the converging lines, not a wick.",
        "Beginners pick the break direction in advance. Measure the triangle's height, wait for the close, then use the height for scale.",
        "Can you know which way a triangle breaks before it does? Type Y or N.", "Hint: compression says when, not where."),
    "elliott": Notes(
        "Elliott wave labels count a move as five waves with the trend and three against it.",
        "It's a story with chapters. The chapters help you know where you are; they don't write the ending.",
        "Wave three is where the crowd joins, wave five is where the last buyers arrive, and the correction is where they learn.",
        "A count is valid only while its rules hold: wave two never retraces all of wave one, wave four never enters wave one's price area.",
        "Beginners relabel every day to fit the chart. Say the rule that would kill the count, and keep the count until it does.",
        "Which wave usually attracts the most volume, three or five? Type 3 or 5.", "Hint: when does the crowd join?"),
    "multiple timeframes": Notes(
        "Multiple timeframe analysis reads the bigger chart for context and the smaller chart for timing.",
        "It's the map and the street view: the map tells you where you are going, the street tells you where to put your feet.",
        "A daily level decides the week; the fifteen-minute chart shows when buyers show up at it.",
        "The timeframes agree when the small-chart structure turns in the direction the big chart allows.",
        "Beginners take a fifteen-minute signal against a daily level. The big chart wins ties.",
        "Which chart decides the direction, the big one or the small one? Type B or S.", "Hint: the map."),
    "replay": Notes(
        "Bar replay hides the future and shows the candles one at a time, the way it felt live.",
        "It's a flight simulator. You can crash as often as you need to learn, and nobody gets hurt.",
        "Looking at a finished chart everything looks obvious; replaying it bar by bar you find out what you actually would have seen.",
        "Honest practice means recording the mistakes, not only the wins.",
        "Beginners replay with the right edge in view. Hide it, decide, then reveal.",
        "Is a pattern easier to spot live or in hindsight? Type L or H.", "Hint: the right edge is a liar."),
    "repainting": Notes(
        "Repainting is when a drawing or indicator value that you saw changes or disappears after more data arrives.",
        "It's a photo that keeps editing itself. What you thought you saw was not what was there.",
        "A swing label needs bars after it to exist, so the latest swing is always provisional; studies on the open candle change until it closes.",
        "A signal is confirmed only on a closed bar, and a higher-timeframe value only when that higher-timeframe bar has closed.",
        "Beginners backtest with values that were not available at the time and get impossible results.",
        "Can the newest swing label on a chart still change? Type Y or N.", "Hint: it needs a future it hasn't had."),
    "default": Notes(
        "The idea is simple once you see it on a real chart, so that's where we'll look.",
        "Think of the chart as footprints: you don't need to see the people to know where they went.",
        "Every move has two sides: the side in control and the side that got trapped. Find the trapped side and the stops explain the rest.",
        "It's real when price reacts at the level more than once and closes confirm it.",
        "Beginners look for the pattern first and the level second. Reverse that.",
        "Where does the idea break: at the level, or at a random price? Type L or R.", "Hint: invalidation."),
}

# transitions and signposts (review-preview, numbered steps), varied by the picker
SIGNPOSTS = {
    "hook": [
        "By the end of this you'll be able to look at {topic} and know in one glance whether it means anything.",
        "Three minutes, one idea: {topic}. Stick around and you'll never read it the same way.",
        "Here's why {topic} matters: it's where most beginners lose money without knowing why. We fix that now.",
        "Quick one, big payoff. {topic}. I'll show you the real thing on the live chart, not a drawing.",
    ],
    "plain": [
        "In plain words: {plain}",
        "Simplest way I can say it: {plain}",
        "Before any jargon: {plain}",
    ],
    "analogy": [
        "{analogy}",
        "Picture it like this. {analogy}",
        "Here's the picture to keep in your head. {analogy}",
    ],
    "point": [
        "Now look at the chart. {chart}",
        "On screen, right here. {chart}",
        "Eyes on the chart. {chart}",
    ],
    "story": [
        "So what actually happened? {story}",
        "Here's the story behind it. {story}",
        "Read it like a story. {story}",
    ],
    "confirm": [
        "What makes it real? {confirm}",
        "Now, confirmation. {confirm}",
        "How do you know it counts? {confirm}",
    ],
    "mistake": [
        "The mistake almost everyone makes: {mistake}",
        "Where beginners go wrong: {mistake}",
        "Quick contrast. {mistake}",
    ],
    "bridge": [
        "So that's {topic}. Next, the part that makes it tradeable: where it's wrong.",
        "That covers {topic}. Now the bit that protects your account.",
        "Good. You've got {topic}. One more layer, then we're done.",
    ],
    "recap": [
        "Recap in one breath. {takeaway} Invalidation: {invalidation}. What to watch next: {watch}.",
        "Let's lock it in. {takeaway} Where it's wrong: {invalidation}. Keep an eye on {watch}.",
        "Three things to take home. One: {takeaway} Two: {invalidation}. Three: watch {watch}.",
    ],
}

_WORD = re.compile(r"[a-z]+")


def notes_for(title: str, body: str = "") -> Notes:
    """Pick the library entry whose key appears in the title first, then the body; else the default."""
    t, b = title.lower(), body.lower()
    keys = [k for k in LIBRARY if k != "default"]
    for k in sorted(keys, key=len, reverse=True):
        if k in t:
            return LIBRARY[k]
    for k in sorted(keys, key=len, reverse=True):
        if k in b:
            return LIBRARY[k]
    return LIBRARY["default"]


def signpost(kind: str, rng: random.Random | None = None, **fmt) -> str:
    rng = rng or random
    line = rng.choice(SIGNPOSTS[kind])
    try:
        return line.format(**fmt)
    except (KeyError, IndexError):
        return line


def arc_description() -> str:
    """The arc as a compact instruction block for the Claude planner prompt."""
    return (
        "THE LESSON ARC (follow this order, one beat per step, more beats only to point at more chart detail):\n"
        "1 hook: why it matters + what they'll be able to do in three minutes.\n"
        "2 plain words: one plain sentence, then an analogy, then the proper name.\n"
        "3 point at it: load the live chart, one marker/highlight at a time, named out loud.\n"
        "4 the story: who was in control, who got trapped, where their stops sat, what the market did.\n"
        "5 confirm / invalidate: what makes it real; put the invalidation hline on the chart and say 'through here the idea is wrong'.\n"
        "6 the mistake: the beginner misread contrasted with the right read.\n"
        "7 check: ONE answerable question for the chat (put it in the beat's 'ask' field; A/B or yes/no style).\n"
        "8 recap in one breath: takeaway, invalidation, what to watch next.\n"
        "Transitions are review-preview: say what you just showed, then what comes next. Numbered signposts for lists, max three."
    )
