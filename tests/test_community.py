"""The community (Telegram) mentions: a hundred distinct wordings, every one compliant and in the house style."""
from __future__ import annotations

import re

from app.brain import community
from app.brain.deai import tells_in
from app.brain.filters import violations
from app.brain.phrases import BANKS, Picker

BAD = re.compile(r"\b(vip|premium|paid|guarantee\w*|profit\w*|income|get rich|dm me|whatsapp|buy now|sell now|entry at|take profit)\b", re.I)
TELEGRAM = re.compile(r"telegram|group", re.I)
NOT_SIGNALS = re.compile(r"signal|calls?|tip|education only|discussion only|nobody|what to (buy|trade|do)|advice|instructions|direction|not (a|for) tak|same rules?|allergic|argu|eyes", re.I)


def test_hundred_distinct_lines():
    assert len(community.LINES) == 100
    assert len({l.strip().lower() for l in community.LINES}) == 100


def test_every_line_names_the_group_and_is_compliant():
    for line in community.LINES:
        full = line.replace("{join}", community.JOIN[0])
        assert TELEGRAM.search(full), full
        assert not BAD.search(full), full
        assert not violations(full), (full, violations(full))
        assert not tells_in(full), (full, tells_in(full))
        assert "—" not in full                      # no em dashes in spoken text


def test_every_spoken_mention_says_what_the_group_is_not():
    import random

    rng = random.Random(3)
    for l in community.LINES:
        spoken = community.with_promise(l, rng).replace("{join}", community.JOIN[2])
        assert NOT_SIGNALS.search(spoken), spoken
        assert not violations(spoken), (spoken, violations(spoken))
        assert not tells_in(spoken), (spoken, tells_in(spoken))


def test_join_paths_are_spoken_not_urls():
    for j in community.JOIN:
        assert "http" not in j and "t.me" not in j
        assert re.search(r"bio", j, re.I)


def test_filter_blocks_a_group_that_shares_signals_but_allows_ours():
    assert violations("Join the Telegram group, we post signals every morning.")
    assert violations("Our channel calls entries daily, link in the bio.")
    assert not violations("The Telegram group is for charts and questions. No signals, no calls. The link is in the bio.")
    assert not violations(community.LINES[0].replace("{join}", community.JOIN[1]))


def test_picker_does_not_repeat_community_wording_for_a_long_run(tmp_path):
    assert BANKS["community"] is community.LINES
    pk = Picker(path=tmp_path / "h.json")
    seen = [pk.pick("community") for _ in range(90)]
    assert len(set(seen)) == 90


def test_schedule_cooldowns():
    import random

    random.seed(1)
    c = community.Community(Picker(path=__import__("pathlib").Path("data_cache/_test_hist.json")), now=1000.0)
    assert c.due_between_lessons(now=1000.0) is False            # not in the opening minutes
    t = 1000.0 + 11 * 60
    hits = sum(1 for _ in range(20) if c.due_between_lessons(now=t))
    assert hits == 1                                               # fires once, then the cooldown holds
    assert c.due_between_lessons(now=t + community.BETWEEN_LESSONS_EVERY_S - 1) is False
