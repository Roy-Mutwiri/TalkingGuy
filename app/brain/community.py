"""The Chart Room community (Telegram): a hundred different ways to mention it, and when to.

The group is for discussion, follow-up questions and chart screenshots. It is education, not a signal
channel: no calls, no entries, nobody tells anyone what to buy. Every line here keeps that promise in
its own words, and the join path is woven in where it fits: the link is in the bio; on TikTok tap it, then
the three dots at the top, then "open in browser".

Spots in the show: once between lessons (after the bridge) and once inside the newcomer hook, each on its own
cooldown, never attached to the risk line or a disclaimer. Lines rotate through the no-repeat picker with a
long memory, so the same wording does not come back within a day.
"""
from __future__ import annotations

import random
import re
import time

BETWEEN_LESSONS_EVERY_S = 28 * 60      # at most one mention between lessons every ~half hour
HOOK_EVERY_S = 50 * 60                 # and one woven into a newcomer hook roughly every 50 minutes
P_BETWEEN = 0.75                       # when the cooldown allows, usually take the spot
P_HOOK = 0.5

JOIN = [
    "The link is in the bio. On TikTok, tap it, hit the three dots at the top, and open it in the browser.",
    "Link's in the bio. Tap it, three dots top right, open in browser, and you're in.",
    "It's one tap from the bio: link, then the three dots up top, then open in browser.",
    "Bio, link, three dots, open in browser. That's the whole trip.",
    "You'll find it in the bio. If TikTok won't open it, the three dots at the top have an open-in-browser option.",
    "Tap the link in the bio. The three dots at the top let you open it in your browser if the app gets stubborn.",
    "The door is the link in the bio. Three dots, open in browser, done.",
]

LINES = [
    # plain and warm
    "Quick one for anyone who wants to keep talking after the lesson: we have a Telegram group for the Chart Room. People post their charts, ask the follow-up questions, argue about structure. No calls, no signals, nobody tells you what to buy. {join}",
    "Some of you ask things that need a longer answer than a live chat can hold. That's what the Telegram group is for. Discussion, screenshots, slow questions. Education only, same as here. {join}",
    "If you like how we read charts here, the conversation keeps going in the Telegram group. Bring a screenshot, say what you see, and the room will pick it apart with you. Nobody there hands out trades. {join}",
    "Housekeeping, thirty seconds. The Chart Room has a Telegram group. It's a classroom, not a tip line: you post a chart, we talk about the structure, the level, where it would be wrong. {join}",
    "The chat scrolls away. The Telegram group doesn't. If you asked something today and I missed it, that's the place to ask it properly. Discussion only, no signals. {join}",
    # story / confession
    "When I blew up my first account I had nobody to show the chart to. That's half of why the Telegram group exists. Post the trade you're unsure about, before or after, and let people tell you what they see. No calls, just eyes. {join}",
    "Someone sent me a screenshot last week with a support line drawn on a wick. Twenty people in the Telegram group explained why it belonged on the body. That's the kind of room it is. Not a signal room, a learning room. {join}",
    "I used to keep a notebook of charts that confused me. The Telegram group is that notebook, except other people answer. Bring the confusing one. {join}",
    "The best lesson I ever got was somebody saying, out loud, that my trendline was wishful thinking. The Telegram group does that for each other. Kindly. Without ever telling you to buy or sell. {join}",
    # questions
    "Where do you go when the lesson ends and the question shows up an hour later? For this room it's the Telegram group. Post it there, I'll pick it up on stream. Nobody in there sells calls. {join}",
    "Who's got a chart on their phone right now they're not sure about? Don't trade it, post it. The Telegram group will read it with you. Education only. {join}",
    "Ever wanted to ask the question you felt was too basic for live chat? That's exactly what the Telegram group is for. No basic questions there, and no signals either. {join}",
    "What do you do with a lesson once it's over? If you want to keep it alive, the Telegram group is where people compare notes on it. Discussion, not tips. {join}",
    # analogies
    "This stream is the lecture. The Telegram group is the study hall after it, where you sit with the others and work through the examples. Nobody in the study hall tells you what to buy. {join}",
    "Think of the stream as the gym floor and the Telegram group as the locker room talk after. Charts, questions, what went wrong, what held. Zero calls. {join}",
    "Live chat is a river. Telegram is a lake. Things you post there stay long enough for someone to actually answer. Education only. {join}",
    "If the Chart Room is the classroom, the Telegram group is the corridor outside it. That's where the honest questions get asked. No signals in the corridor either. {join}",
    "A chart on your own is a mirror; you see what you want. A chart in the Telegram group is a window; people see what's there. That's the point of it. No trade calls, ever. {join}",
    # for newcomers
    "If you just walked in: there's a Telegram group for this room. It's free, it's for discussion and chart screenshots, and nobody there will tell you what to trade. {join}",
    "New here? Two things. One, nothing on this stream is advice. Two, the longer conversation lives in the Telegram group, where you can post your own charts and ask slowly. {join}",
    "For the people who found this stream five minutes ago: welcome, and yes, there's a place to keep talking when I'm busy drawing. The Telegram group. Discussion only. {join}",
    "Quick orientation for newcomers. I teach here, I don't tip. The Telegram group follows the same rule and adds one thing: you can bring your own chart. {join}",
    # screenshots
    "Homework, if you want it: screenshot a chart you're watching, mark the level you think matters, and post it in the Telegram group. Say why. The why is the lesson. No calls. {join}",
    "Post your markup in the Telegram group. Not the trade, the markup. Where's the structure, where's the level, where would it be wrong. {join}",
    "Here's a habit that fixes beginners fast: before you touch anything, post the chart in the Telegram group and write one sentence on what you see. People will answer. Nobody will tell you to buy. {join}",
    "If you drew a trendline today, screenshot it and drop it in the Telegram group. The room is good at telling you whether it's a line or a wish. {join}",
    "The chart you're least sure about is the one worth posting. Telegram group, screenshot, one line of reasoning. Discussion, not instructions. {join}",
    # callbacks / continuity
    "The question about wicks from earlier is a Telegram question. Too long for live chat. Post it there and I'll come back to it properly on stream. {join}",
    "A few of you asked about the invalidation idea last night. There's a thread on it in the Telegram group. Read it, argue with it, add your example. No calls in there. {join}",
    "Somebody asked where the lesson notes live. There aren't notes, but the Telegram group remembers. People summarise, people argue, people post the charts. {join}",
    "If you were here yesterday for the structure lesson, the follow-up conversation is in the Telegram group. That's where the examples pile up. Education only. {join}",
    # humour
    "I don't have a signal group. I have a Telegram group where people tell each other their lines are crooked. Much more useful. {join}",
    "Telegram group, yes. Signals, no. If anyone in there ever tells you to buy something, screenshot them and send it to me, that's not what the room is for. {join}",
    "People ask if there's a secret inner circle. There's a free Telegram group full of people correcting each other's chart markups. That's as inner as it gets, and nobody in it sells calls. {join}",
    "No, the Telegram group isn't where the real signals are. There are no real signals. It's where the real questions are. {join}",
    "The Telegram group has one rule I actually enforce: bring charts, not calls. Everything else is fair game. {join}",
    # trading-brain framing
    "Trading alone is how most people lose. Not because they're wrong, because nobody checks their thinking. The Telegram group is the check. Post the thinking, not the trade. {join}",
    "The hardest part of this game is seeing your own bias. A group of people reading the same chart cures that faster than anything. That's what the Telegram group is. Discussion only. {join}",
    "Most beginners don't need more indicators, they need someone to ask what the level means. Ask it in the Telegram group. Nobody there will answer with a trade. {join}",
    "Your edge isn't a secret indicator. It's reviewing your charts with people who don't care about your feelings. The Telegram group is that, with manners. {join}",
    # short and quick
    "Telegram group, link in the bio. Discussion and charts, no calls. That's all. Back to the chart.",
    "Reminder: the follow-up conversation is in the Telegram group. Education only. {join}",
    "Charts, questions, screenshots: Telegram group. Signals: nowhere. {join}",
    "If you want the slower conversation, it's in the Telegram group. {join}",
    "Longer questions go to the Telegram group. Link's in the bio. Zero signals, lots of charts.",
    # between-lessons specific
    "Before the next lesson: if that one raised a question, the Telegram group is where to put it. I read it between sessions. No calls in there, just charts and talk. {join}",
    "Lesson's done. If part of it didn't land, don't sit on it. Ask in the Telegram group, people will walk you through it with their own examples. Education only. {join}",
    "While the next chart loads: the Telegram group exists for exactly this gap, when you have a thought and the stream has moved on. Post it there. {join}",
    "One more thing before we move. The Telegram group. Free, discussion only, screenshot friendly, allergic to signals. {join}",
    "Good moment to mention the Telegram group, since we just finished a lesson. Take the idea there, test it on your own chart, post what you found. No trade calls, ever. {join}",
    # time-of-day
    "For the night owls: I'm here all night, but the Telegram group is where the day shift left their charts. Go read what they found. Discussion only. {join}",
    "Weekend crowd, the market's quiet but the Telegram group isn't. People review the week's charts there. No calls, just review. {join}",
    "London just opened and the Telegram group is usually buzzing around now with people posting what gold did overnight. Join the review. Nobody gives trades. {join}",
    "Market's slow right now. Good time to tell you about the Telegram group: it's where the chart reviews happen when the stream is quiet. Education only. {join}",
    # honesty framing
    "Full honesty about the Telegram group: it won't make you money. It'll make you better at reading a chart, which is a different thing and the only thing I can actually offer. {join}",
    "I'll say what the Telegram group is not. Not a signal service, not a paid room, not a place anyone tells you what to do with your money. It's a classroom that never closes. {join}",
    "If a group promises signals, leave. If a group argues about where a level belongs, stay. Ours is the second kind. {join}",
    "The Telegram group has exactly the same rules as this stream. Nobody predicts, nobody calls, everyone learns. {join}",
    # inviting participation
    "The best threads in the Telegram group start with a bad chart. Post your worst one. I mean it. {join}",
    "If you've been watching for a week and never said anything, the Telegram group is the easy first step. Post a chart, type one sentence. {join}",
    "Lurkers, this one's for you. The Telegram group is lower pressure than live chat. Nobody's watching you type. Charts and questions only. {join}",
    "You don't need to be good to post in the Telegram group. You need to be curious. That's the entry requirement. No signals inside. {join}",
    # specific skills
    "If you're working on structure, highs and lows, the Telegram group has a running thread of examples people posted. Add yours. Discussion only. {join}",
    "For everyone practising support and resistance: post three levels from your own chart in the Telegram group and let people tell you which one is real. {join}",
    "The Telegram group is where the Fibonacci arguments happen, and they're good arguments. Bring yours. Nobody ends an argument with a trade call. {join}",
    "Timeframe confusion is the most common question in the Telegram group. If that's you, you're in good company. Post the two charts that disagree. {join}",
    # proof-of-work style
    "Something I like about the Telegram group: people post the trade after it closed, win or lose, and explain what they saw. That honesty teaches more than any win. Join them. {join}",
    "In the Telegram group people post losses with the chart. Nobody laughs, everybody learns. That's rare and that's why I keep mentioning it. No signals. {join}",
    "If you want to see how other beginners mark up gold, the Telegram group is a live gallery of it. Add your own. Discussion, not direction. {join}",
    # tying to the current moment
    "What we're drawing right now would be a good thing to redraw yourself and post in the Telegram group. See if your levels match mine. If they don't, say why. {join}",
    "Take this chart, do it yourself on your own screen, and drop the result in the Telegram group. That's how it sticks. No calls in there, just comparison. {join}",
    "Pause the lesson in your head for a second. This exact setup, posted in the Telegram group with your own reading, would get you ten honest replies. {join}",
    # gentle nudges
    "Not everything fits in a live chat. The Telegram group is the overflow. Education only, and the link is in the bio.",
    "If I missed your question, it's not gone. Put it in the Telegram group and it waits for me. {join}",
    "The Telegram group is free and it stays free. It's for talking charts, not for taking trades. {join}",
    "You can watch here and never join anything, that's fine. But if you want people to think with, the Telegram group is where they are. {join}",
    # contrast lines
    "Live chat is for reactions. The Telegram group is for reasons. Post the reason. {join}",
    "Here I talk and you listen. In the Telegram group you talk and people listen. Charts, questions, no calls. {join}",
    "On stream I draw the levels. In the Telegram group you draw them and get told what's off. That's the better half of learning. {join}",
    "Stream is one voice. Telegram is a room full of them, all looking at the same chart. Nobody in it gives trades. {join}",
    # unusual openers
    "Confession: I check the Telegram group between lessons more than I check the price. The questions in there are better than the price. Join if you want yours read. {join}",
    "Small ask, no pressure. If this stream helped you read a chart, go help someone else read theirs in the Telegram group. That's how the room grows. {join}",
    "I want to see your charts, not your trades. Telegram group. {join}",
    "There's a version of this room where you talk back. It's the Telegram group. {join}",
    "People keep asking where the community is. It's on Telegram. It's free. It's about charts, not calls. {join}",
    # risk-aware framing (not the risk line itself)
    "If a trade went against you this week, the most useful thing you can do is post the chart in the Telegram group and ask what you missed. That's how it stops happening twice. {join}",
    "Losses get quieter when you talk about them. The Telegram group is where people do that, with the chart attached. No signals, just the post-mortem. {join}",
    "Before you ever risk money on an idea, say it out loud to someone. The Telegram group is the someone. {join}",
    # meta / self-aware
    "Yes, I mention the Telegram group a lot. Because a lot of you ask where to continue the conversation. It's there. Charts, questions, no calls. {join}",
    "I'll keep this one short because I said it an hour ago in a longer way: Telegram group, bio, discussion only.",
    "If you've heard me mention the group already, this is for whoever just arrived: the Chart Room has a Telegram group for charts and questions. {join}",
    # final set
    "Bring a question you've been embarrassed to ask. The Telegram group was built for that question. No signals in there, only answers. {join}",
    "If this lesson made you want to redraw your own chart, do it, then post it in the Telegram group. Compare, don't copy. {join}",
    "The people who improve fastest here are the ones who post in the Telegram group every day. Not trades. Charts and questions. {join}",
    "There's a thread in the Telegram group for every lesson we do. Find today's, add your example, read the others. Education only. {join}",
    "Chart Room, Telegram, free, discussion. Four words that belong together. {join}",
    "If you want this to be more than background noise while you cook dinner, the Telegram group is where it becomes a habit. Charts and questions, no calls. {join}",
    "I read the Telegram group before every session. If you want to shape what I teach next, that's where you say it. {join}",
    "Nobody learns this alone. The Telegram group is the room where you don't have to. Discussion only, no signals. {join}",
    "Last one on this, then back to the chart: Telegram group, link in the bio, bring charts, leave the signals at the door.",
]

assert len(LINES) == 100, len(LINES)


NOT_SIGNALS_RE = re.compile(r"signal|calls?\b|tip|education only|discussion only|nobody|what to (buy|trade|do)|advice|instructions|direction|not (a|for) tak|same rules?|allergic|argu|eyes", re.I)
TAILS = [
    "No signals in there, just charts.",
    "Education only, same as here.",
    "Nobody there tells you what to trade.",
    "Discussion only. Zero calls.",
    "Charts and questions, never signals.",
    "Same rules as the stream: no calls, no tips.",
    "It's a classroom, not a tip line.",
    "Nobody in it gives trades. That's the deal.",
    "Talk, not tips.",
    "No signals, no DMs, no selling. Just the chart.",
]


def with_promise(text: str, rng: random.Random | None = None) -> str:
    """Every spoken mention carries the promise in some wording: what the group is not."""
    if NOT_SIGNALS_RE.search(text):
        return text
    rng = rng or random
    tail = rng.choice(TAILS)
    if "{join}" in text:
        return text.replace("{join}", tail + " {join}")
    return text.rstrip() + " " + tail


class Community:
    """Decides when a community mention fits and renders it with a join path, never the same wording twice in a day."""

    def __init__(self, picker, enabled: bool = True, now: float | None = None) -> None:
        self.picker = picker
        self.enabled = enabled
        now = time.time() if now is None else now
        # first mentions about ten minutes into a session, not in the opening breath
        self.last_between = now - BETWEEN_LESSONS_EVERY_S + 10 * 60
        self.last_hook = now - HOOK_EVERY_S + 10 * 60
        self.said = 0

    def line(self) -> str:
        text = with_promise(self.picker.pick("community"))
        join = random.choice(JOIN)
        return text.replace("{join}", join).strip()

    def due_between_lessons(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if not self.enabled or now - self.last_between < BETWEEN_LESSONS_EVERY_S:
            return False
        if random.random() > P_BETWEEN:
            return False
        self.last_between = now
        self.said += 1
        return True

    def due_in_hook(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if not self.enabled or now - self.last_hook < HOOK_EVERY_S:
            return False
        if random.random() > P_HOOK:
            return False
        self.last_hook = now
        self.said += 1
        return True
