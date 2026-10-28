"""Phrase banks with a no-repeat picker, used wherever the teacher speaks without the
LLM (intro, bridges between lessons, market tour, template lessons, fallbacks).

Every bank has many variants; `Picker.pick` never returns one of the last N picks
of that bank, and the history is persisted so a restart does not reset the pattern.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

STATE = Path("data_cache/phrase_history.json")

BANKS: dict[str, list[str]] = {
    "greeting": [
        "Hey, welcome in. This is the Chart Room, I'm Haddan. Think of me as the friend who sits next to you and explains the chart while it moves.",
        "Good to see you. Chart Room is live, I'm Haddan. This is education only, and the chat is open, so ask me anything.",
        "Welcome, grab a seat. Haddan here, this is the Chart Room. No signals, no hype, just charts explained properly.",
        "If you just walked in, hi. I'm Haddan. I read the chat between lessons, so throw your questions at me.",
        "Chart Room, live again. Haddan on the mic, and my only job is to make charts make sense. Let's get into it.",
        "Hello hello. Haddan here. We're live around the clock, so wherever you are, it's chart time.",
        "Welcome in. Some of you call me Sir Haddan, I'll take it. Chart's up, chat's open, let's read it together.",
    ],
    "bridge": [
        "Let me check the chat before we move on.",
        "Questions? Drop them now, I'll answer before the next lesson.",
        "Okay, next one coming up. If you just joined, say hi in the chat.",
        "Quick breather. Chat, what's on your mind?",
        "Before the next lesson, let me see who's here.",
        "Alright. New chart, new lesson, same rules: context first.",
        "That one's done. Let's see what the chat is saying.",
        "One down. Next lesson in a moment, questions first.",
        "Stretch your legs. I'm reading the chat.",
        "That's the lesson. Let me take a question or two.",
        "Cool. I'll grab a question if there is one, then we move.",
        "Pause. Chat time.",
    ],
    "disclaimer": [
        "Quick reminder, this is education, not financial advice. I teach, you decide.",
        "Nothing here is a signal. I show you how to read a chart, you decide what to do with your own risk.",
        "I never know where price goes next. Nobody does. We work with levels and invalidation, not predictions.",
        "Friendly reminder: I teach, I don't tip. Your money, your decisions.",
        "If anyone in the chat is selling you signals, that's not me and it's not this stream.",
        "Education only. The moment someone promises you returns, close the tab.",
    ],
    "boring": [
        "Honestly, the chart is boring right now. And boring is information: nobody wants to commit.",
        "Not much happening. That's fine. Most of trading is waiting.",
        "Price is just drifting. Beginners force trades here. Pros make tea.",
        "This is the kind of chart that eats impatient people. Let it be boring.",
    ],
    "mistake": [
        "Mistake of the day: moving your stop further away because price is getting close to it. The stop was the plan. Moving it is the ego.",
        "Mistake of the day: adding to a loser. You were wrong once, now you're wrong with more size.",
        "Mistake of the day: trading the one minute chart because the four hour was too slow. The four hour was telling you to wait.",
        "Mistake of the day: calling every green candle a reversal. One candle is a sentence, not the whole story.",
        "Mistake of the day: no invalidation. If you can't say where you're wrong, you don't have a trade, you have a hope.",
        "Mistake of the day: revenge trading after a loss. The market doesn't know you lost. It doesn't owe you anything.",
        "Mistake of the day: watching a win turn into a loss because taking profit felt like quitting. Plans beat feelings.",
        "Mistake of the day: thinking more indicators means more certainty. They all read the same price.",
    ],
    "lesson_open": [
        "Let's talk about {topic}. Here's {market} on the {tf} chart. I'll let the candles come in one by one.",
        "New lesson: {topic}. {market}, {tf} chart. Watch how this develops.",
        "Okay, {topic}. I pulled up {market} on the {tf}. Let the candles draw in, then we'll read them.",
        "This one's about {topic}. {market}, {tf} timeframe. Follow the candles as they print.",
        "Time for {topic}. On screen, {market}, {tf} chart. Keep your eyes on how price gets here.",
        "{topic}. That's the lesson. Chart is {market}, {tf}. Let's read it together.",
        "Here's a good one: {topic}. {market} on the {tf}. I'm going to replay the move so you see it build.",
        "Next up, {topic}. {market}, {tf}. First the candles, then the story.",
    ],
    "lesson_recap": [
        "Recap in one breath: {takeaway} Context first, pattern second, and always know where you're wrong.",
        "So, what do you take home? {takeaway} And never without an invalidation.",
        "Bottom line: {takeaway} If you remember one thing, remember that.",
        "Let's close it. {takeaway} Where would you have been wrong? At the level. Always at the level.",
        "Summing up: {takeaway} That's it. No magic, just location and patience.",
        "The takeaway: {takeaway} Write it down somewhere you'll see it.",
    ],
    "market_intro": [
        "Quick live look at {market} on the {tf} chart.",
        "Let's peek at the real thing. {market}, {tf}, live candles.",
        "Live chart time. This is {market} right now, {tf} candles, updating as we speak.",
        "Here's {market} as it trades right now, {tf} chart.",
        "Live market check. {market}, {tf}.",
    ],
    "market_describe": [
        "Price is around {price}, {direction} about {chg} percent over the last day. The last twenty-four hours ran between {lo} and {hi}, and right now we sit {where} that range.",
        "We're trading near {price}. Over the day that's {direction} {chg} percent. Range so far: {lo} to {hi}, and price is {where} it.",
        "Current price about {price}, {direction} {chg} percent on the day. The day's low is {lo}, the high is {hi}, and we're {where} that box.",
    ],
    "market_lesson": [
        "Notice how the candles update live. The reaction at the edges of the range is the information, not the level itself.",
        "If you were studying this, you'd mark the range high and low and wait to see whether price gets accepted outside or rejected. Patience is the skill.",
        "A range like this is where beginners get chopped. Let the market show its hand first, and always know where you'd be wrong.",
        "Watch the wicks near the edges. Long wicks mean someone tried and got refused.",
        "Nothing to do here is also a decision. Sitting out is a position.",
        "See how volume dries up in the middle of the range? Nobody is interested in the middle. Interest lives at the edges.",
        "The level that matters most is the one price keeps coming back to. Mark it, then watch the reaction.",
        "I don't know where this goes next, and neither does anyone else. What I know is where the idea would be wrong.",
    ],
    "no_question_filler": [
        "No questions in the chat right now, so let me give you a little something.",
        "Chat's quiet. Good. Quiet chats are where people actually learn.",
        "Nobody's asking, so I'll ask you one. Where was the last swing low on this chart? Say it in the chat.",
        "Quiet moment. Let me use it well.",
    ],
    "welcome": [
        "Welcome in, {names}. Grab a seat, we're reading charts.",
        "{names}, hey. You picked a good time, we're on {topic}.",
        "New faces: {names}. Chat's open, ask me anything about the chart.",
        "{names} just walked in. Quick context: {topic}. Stay for it.",
        "Hey {names}. If you only stay two minutes, stay for the next one.",
        "{names}, welcome. No signals here, just how to read what's in front of you.",
    ],
    "thanks_follow": [
        "{name} just followed. Appreciate you. That's one more person who'll know where their stop goes.",
        "Follow from {name}, thank you. Welcome to the chart room.",
        "{name}, thanks for the follow. I'll remember that.",
        "New follow, {name}. Respect. We go live around the clock, so you'll always find me.",
    ],
    "thanks_gift": [
        "{name} sent {gift}. Thank you, that's generous. Doesn't change the lesson, but it changes my mood.",
        "A {gift} from {name}. Appreciated. Okay, back to the chart with extra energy.",
        "{name}, thank you for the {gift}. Chat, say thanks to {name}.",
    ],
    "thanks_share": [
        "{name} shared the stream. Thank you, that's how new people find the room.",
        "Share from {name}. That matters more than you think. Appreciated.",
    ],
    "likes": [
        "Likes are flying in. Keep them coming, it pushes the room to new people.",
        "Chat, tap the screen a few times for me. It helps the stream get seen.",
    ],
    "hook": [
        "If you just joined: we're on {topic}. In the next two minutes you'll see exactly where the idea would have failed. Stay.",
        "New here? Quick version: {topic}. The part most people get wrong is coming up next.",
        "Just arrived? Perfect timing. {topic}, and I'm about to show you the mistake that costs beginners the most.",
        "If you're scrolling past, give me ninety seconds. {topic}. Then decide.",
        "For the people who just landed: {topic}. I'll show it on a real chart, not a drawing.",
    ],
    "chat_prompt": [
        "Quick one for the chat: type 1 if you've ever moved a stop loss further away. Be honest.",
        "Chat, where's the last swing low on this chart? Type the price, I'll check.",
        "Type your main market in the chat. Gold, crypto, forex, stocks. I'll pick the next lesson from it.",
        "Be honest in the chat: how many indicators are on your chart right now?",
        "Chat, up or down from here? Don't think, type. Then I'll show you why it doesn't matter.",
        "One word in the chat: what's the hardest part of trading for you? I read everything.",
        "Type the timeframe you trade. I'll tell you the mistake that goes with it.",
    ],
    "countdown": [
        "Live chart in ten seconds. Call the direction in the chat, zero shame.",
        "Ten seconds, then we look at the real thing. Guess the range in the chat.",
        "Okay, countdown. Ten seconds until the live chart. Get your calls in.",
    ],
    "ai_honest": [
        "Straight talk for a second: I don't run a signal group, I don't take DMs, and I'm not selling a course. The chart is the whole product.",
        "Honesty corner. I don't know where price goes next, and neither does anyone selling you certainty. We work with levels and where the idea is wrong.",
        "One thing about this room: nobody here is going to tell you what to buy. I show you how to read it, you own the decision.",
    ],
    "hint": [
        "{hint}",
        "[chuckle] No pressure. {hint}",
        "Still open. {hint}",
    ],
    "celebrate": [
        "{name}, you spotted it! {detail} That's the detail. Let's look at why it matters.",
        "[laugh] Yes, {name}! {detail} Exactly the thing to notice.",
        "[laughs] {name} nailed it: {detail} Love that. Here's why it matters.",
        "[chuckle] Oh nice, {name}, that's it. {detail} Let's see it on the chart.",
    ],
    "no_answers": [
        "[chuckle] No takers yet, all good. Here's the answer, and then we keep moving.",
        "Chat's thinking. Let me show you the answer and you'll see it next time.",
        "[sighs] Nobody bit, fair enough. The answer, then straight on.",
    ],
    "bridge_exchange": [
        "Good exchange. That ties straight into the next bit on {topic}.",
        "Love that. And it leads right into what's next: {topic}.",
        "Okay, that's a great segue. Back to {topic}, and watch what changes.",
        "Perfect, keep those coming. Now, {topic}: the part that matters.",
    ],
    "quiet_observation": [
        "Quick look at the live chart: {symbol} is at {price}, {chg} on the day. That's the number to keep in the corner of your eye.",
        "While chat's quiet: {symbol} sitting at {price}, {chg} today. Nothing dramatic, which is itself information.",
        "Live check. {symbol} {price}, {chg} on the day. Watch how it treats the last level we marked.",
    ],
    "mini_challenge": [
        "Okay, this is the interesting part. On {topic}, which detail would you check first? Type it, I'll pick one.",
        "Mini challenge: find the level on screen that matters most for {topic}. One word in the chat.",
        "Quick one for the chat: wick or close, which one confirms it? Type W or C.",
        "Challenge while it's quiet: up or down from here? Don't think, type. Then I'll show you why it doesn't matter.",
    ],
}


class Picker:
    def __init__(self, path: Path = STATE, memory: int = 6) -> None:
        self.path = path
        self.memory = memory
        self.history: dict[str, list[int]] = {}
        try:
            if path.exists():
                self.history = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            self.history = {}

    def pick(self, bank: str, **fmt) -> str:
        options = BANKS[bank]
        used = self.history.get(bank, [])[-min(self.memory, len(options) - 1):] if len(options) > 1 else []
        choices = [i for i in range(len(options)) if i not in used] or list(range(len(options)))
        i = random.choice(choices)
        self.history.setdefault(bank, []).append(i)
        self.history[bank] = self.history[bank][-50:]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.history))
        except Exception:  # noqa: BLE001
            pass
        text = options[i]
        try:
            return text.format(**fmt) if fmt else text
        except (KeyError, IndexError):
            return text
