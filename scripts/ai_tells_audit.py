"""Audit Haddan's language for AI-writing tells (Wikipedia: Signs of AI writing).

    python scripts/ai_tells_audit.py            # banks + the last 2000 spoken lines in logs/stream.log

Reports: tells found in the static phrase banks, teaching library and showman lines (should be zero),
and how often the brain produced a tell that the scrubber had to fix (from `deai:` log lines) against
how many utterances went out (`say:` lines).
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.brain import showman, teaching  # noqa: E402
from app.brain.deai import tells_in  # noqa: E402
from app.brain.phrases import BANKS  # noqa: E402


def static_lines() -> list[tuple[str, str]]:
    out = []
    for bank, lines in BANKS.items():
        out += [(f"phrases:{bank}", l) for l in lines]
    for name in dir(showman):
        v = getattr(showman, name)
        if isinstance(v, list) and v and isinstance(v[0], str):
            out += [(f"showman:{name}", l) for l in v]
    for k, n in teaching.LIBRARY.items():
        out += [(f"teaching:{k}", getattr(n, f)) for f in ("plain", "analogy", "story", "confirm", "mistake", "check", "hint")]
    for kind, lines in teaching.SIGNPOSTS.items():
        out += [(f"signpost:{kind}", l) for l in lines]
    return out


def main() -> None:
    bad = [(src, t, line[:80]) for src, line in static_lines() for t in tells_in(line)]
    print(f"static lines audited: {len(static_lines())}; tells: {len(bad)}")
    for src, t, line in bad[:30]:
        print(f"  - {src}: {t} | {line}")
    log = ROOT / "logs" / "stream.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()[-20000:]
        says = [l for l in lines if " director: say: " in l][-2000:]
        fixes = [l for l in lines if " director: deai: " in l][-2000:]
        kinds = Counter()
        for l in fixes:
            m = re.search(r"\[(.*?)\]", l)
            if m:
                for k in m.group(1).split(","):
                    kinds[k.strip().strip("'")] += 1
        print(f"\nspoken utterances in log: {len(says)}; utterances the scrubber had to fix: {len(fixes)} ({(len(fixes) / max(len(says), 1)) * 100:.1f}%)")
        for k, n in kinds.most_common(12):
            print(f"  - {k}: {n}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
