"""Live music maker: keeps the `music/` folder topped up with ORIGINAL beats while the stream runs.

    .venv\\Scripts\\python -m app.voice.music_maker            # loop forever (started by supervise.ps1)
    .venv\\Scripts\\python -m app.voice.music_maker --once     # make one track and exit (timing check)

Runs Meta's MusicGen (small) on the CPU at below-normal process priority, so it never competes with the
voice for the GPU and never starves the audio thread. One new 30 s beat every few minutes; when the pool is
full the oldest generated beats are retired, so the bed keeps changing all day instead of looping the same
handful. Files are written to a temp name and renamed, so the bed never picks up a half-written track.

.env knobs: MUSIC_MAKER=0 disables it; MUSIC_MAKER_DEVICE=cuda uses the GPU (only if the voice is online/Edge);
MUSIC_MAKER_EVERY_S (default 240) spacing between tracks; MUSIC_MAKER_TARGET (default 60) pool size to reach quickly;
MUSIC_MAKER_MAX (default 150) cap before the oldest generated beats are deleted; MUSIC_MAKER_STYLE haddan|mix|arabic.
Beats you put in the folder yourself (any name not starting with beat_) are never deleted.
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
log = logging.getLogger("music_maker")

MUSIC = ROOT / "music"
EVERY_S = float(os.getenv("MUSIC_MAKER_EVERY_S", "240"))
TARGET = int(os.getenv("MUSIC_MAKER_TARGET", "60"))
MAX_TRACKS = int(os.getenv("MUSIC_MAKER_MAX", "150"))
STYLE = os.getenv("MUSIC_MAKER_STYLE", "haddan").lower()
DEVICE = os.getenv("MUSIC_MAKER_DEVICE", "cpu").lower()
MODEL = os.getenv("MUSIC_MAKER_MODEL", "facebook/musicgen-small")
SECONDS = int(os.getenv("MUSIC_MAKER_SECONDS", "30"))


def _lower_priority() -> None:
    try:
        import psutil

        p = psutil.Process()
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)
    except Exception as exc:  # noqa: BLE001
        log.debug("priority: %s", exc)


def _prompts() -> list[str]:
    from make_music import ARABIC, HADDAN, PROMPTS  # scripts/make_music.py holds the prompt banks

    if STYLE == "arabic":
        return ARABIC
    if STYLE == "mix":
        return PROMPTS
    return HADDAN * 3 + PROMPTS      # Haddan's styles three times as likely as the rest


def _generated() -> list[Path]:
    return sorted((p for p in MUSIC.glob("beat_*.wav")), key=lambda p: p.stat().st_mtime)


def _next_index() -> int:
    nums = []
    for p in MUSIC.glob("beat_*.wav"):
        try:
            nums.append(int(p.stem.split("_")[1]))
        except (IndexError, ValueError):
            pass
    return (max(nums) + 1) if nums else 1


class Maker:
    def __init__(self) -> None:
        import torch
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        self.torch = torch
        if DEVICE == "cpu":
            torch.set_num_threads(max(2, min(8, (os.cpu_count() or 8) // 3)))
        self.device = "cuda" if DEVICE == "cuda" and torch.cuda.is_available() else "cpu"
        t0 = time.time()
        self.processor = AutoProcessor.from_pretrained(MODEL)
        self.model = MusicgenForConditionalGeneration.from_pretrained(MODEL).to(self.device)
        self.model.eval()
        self.sr = int(self.model.config.audio_encoder.sampling_rate)
        self.prompts = _prompts()
        self.recent: list[str] = []
        log.info("MusicGen loaded on %s in %.0fs (threads %d)", self.device, time.time() - t0, torch.get_num_threads())

    def one(self) -> Path:
        import numpy as np
        import soundfile as sf

        pool = [p for p in self.prompts if p not in self.recent[-6:]] or self.prompts
        prompt = random.choice(pool)
        self.recent.append(prompt)
        inputs = self.processor(text=[prompt], padding=True, return_tensors="pt").to(self.device)
        t0 = time.time()
        with self.torch.no_grad():
            audio = self.model.generate(**inputs, do_sample=True, guidance_scale=3.0, max_new_tokens=int(SECONDS * 50))
        wav = audio[0, 0].cpu().numpy().astype(np.float32)
        peak = float(np.abs(wav).max()) or 1.0
        wav = wav / peak * 0.9
        # a short fade in/out so the loop point is never a click
        n = int(self.sr * 0.4)
        if wav.size > 2 * n:
            ramp = np.linspace(0, 1, n, dtype=np.float32)
            wav[:n] *= ramp
            wav[-n:] *= ramp[::-1]
        slug = prompt.split(",")[0].replace(" ", "_").replace("-", "_")[:28]
        final = MUSIC / f"beat_{_next_index():02d}_{slug}.wav"
        tmp = final.with_suffix(".part.wav")
        sf.write(tmp, wav, self.sr)
        tmp.replace(final)
        log.info("made %s (%.0fs audio in %.0fs)", final.name, wav.size / self.sr, time.time() - t0)
        return final

    def prune(self) -> None:
        gen = _generated()
        while len(gen) > MAX_TRACKS:
            victim = gen.pop(0)
            try:
                victim.unlink()
                log.info("retired %s", victim.name)
            except OSError:
                break


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="make one track and exit")
    a = ap.parse_args()
    (ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(),
                                  logging.handlers.RotatingFileHandler(ROOT / "logs" / "music_maker.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")])
    for noisy in ("transformers", "torch", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.ERROR)
    if os.getenv("MUSIC_MAKER", "1") == "0" and not a.once:
        log.info("MUSIC_MAKER=0: not running")
        return
    MUSIC.mkdir(exist_ok=True)
    _lower_priority()
    maker = Maker()
    if a.once:
        maker.one()
        return
    last = 0.0
    while True:
        try:
            have = len(_generated())
            due = time.time() - last >= EVERY_S
            if have < TARGET or due:
                maker.one()
                maker.prune()
                last = time.time()
            else:
                time.sleep(10)
        except Exception as exc:  # noqa: BLE001
            log.warning("maker: %s", exc)
            time.sleep(60)


if __name__ == "__main__":
    main()
