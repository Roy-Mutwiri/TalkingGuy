"""Render a short Haddan segment through the live voice chain so you can hear the human layer.

    .venv\\Scripts\\python scripts\\human_demo.py            # -> data_cache/voice_samples/human_demo.wav (+ _plain.wav)

Uses the engine from .env (chatterbox if installed, else edge). Stop the stream first when the GPU voice is on,
so the two do not fight for the card. The _plain file is the same words with the delivery plan switched off,
for an A/B listen.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.voice import make_speaker  # noqa: E402
from app.voice.disfluency import Imperfections, humanize_text  # noqa: E402
from app.voice.edge_voice import _seed  # noqa: E402
from app.voice.human import describe, plan_sentence  # noqa: E402
from app.voice.humanize_audio import humanize_sentence  # noqa: E402
from app.voice.kokoro_tts import split_sentences  # noqa: E402
from app.voice.pronounce import humanize  # noqa: E402

SEGMENT = (
    "Maria, good one. Welcome back, this is the wick thing from yesterday. "
    "Okay, look at this. Gold pushed into 3,912, got rejected, and came straight back into the range. "
    "First, the level held twice before. Second, the push had no follow-through. Third, the close is back inside. "
    "The stop goes where the idea is wrong, below that low, and if price trades through it the story is over. "
    "Which detail would you check first? Type it in the chat, I'll wait."
)


def main() -> None:
    engine = os.getenv("TTS_ENGINE", "edge")
    sp = make_speaker(engine, device=os.getenv("AUDIO_DEVICE", "CABLE Input"))
    sp.mood = "teach"
    if hasattr(sp, "_load"):
        sp._load()
    out_dir = ROOT / "data_cache" / "voice_samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    text = humanize_text(humanize(SEGMENT), "teach", seed=3)
    text = Imperfections().apply(text, "teach")
    sents = split_sentences(text)
    t0 = time.time()
    raw = sp.synth_many(sents)
    print(f"synthesised {len(sents)} sentences in {time.time() - t0:.1f}s on {engine}")
    human_parts, plain_parts = [], []
    prev_len = 0
    for i, (s, a) in enumerate(zip(sents, raw)):
        rng = np.random.default_rng(_seed(s))
        plan = plan_sentence(s, mood="teach", index=i, total=len(sents), rng=rng, engine_sets_rate=sp.engine == "edge")
        print(f"  [{describe(plan)}]  {s}")
        human_parts.append(humanize_sentence(a, sp.out_rate, first=i == 0, long_prev=prev_len > 90, mood="teach", seed=_seed(s), plan=plan))
        plain_parts.append(humanize_sentence(a, sp.out_rate, first=i == 0, long_prev=prev_len > 90, mood="teach", seed=_seed(s)))
        prev_len = len(s)
    human = np.concatenate(human_parts)
    plain = np.concatenate(plain_parts)
    sf.write(out_dir / "human_demo.wav", human, sp.out_rate)
    sf.write(out_dir / "human_demo_plain.wav", plain, sp.out_rate)
    print(f"wrote {out_dir / 'human_demo.wav'} ({human.size / sp.out_rate:.1f}s) and human_demo_plain.wav ({plain.size / sp.out_rate:.1f}s)")


if __name__ == "__main__":
    main()
