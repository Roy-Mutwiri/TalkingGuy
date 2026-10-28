"""Expressive local voice: Chatterbox-Turbo (Resemble AI, MIT) on the GPU.

It performs non-verbal tags inline: [laugh] [chuckle] [sigh] [clear throat] [gasp] [groan] [sniff] [cough] [shush].
The timbre comes from a reference clip; ours is synthetic (app/voice/ref/theo_ref.wav, rendered from an
Edge voice), so no real person's voice identity is cloned. Mood maps to the model's exaggeration knob.

Playback, caching, sentence streaming and the broadcast mic chain are inherited from EdgeSpeaker;
only synthesis is replaced.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

import numpy as np

from .edge_voice import EdgeSpeaker, FETCH_TIMEOUT_S

log = logging.getLogger("voice")
os.environ.setdefault("TQDM_DISABLE", "1")      # the model prints token progress bars; not in a 24/7 log
DEFAULT_REF = Path(__file__).resolve().parent / "ref" / "haddan_own_c.wav"

# mood -> (exaggeration, cfg_weight, temperature). Exaggeration raises intensity; cfg_weight 0.5 keeps pace natural.
MOOD_PARAMS = {
    "teach": (0.45, 0.5, 0.8), "show": (0.6, 0.45, 0.85), "hype": (0.75, 0.4, 0.9), "excited": (0.8, 0.4, 0.9),
    "cheerful": (0.6, 0.45, 0.85), "warm": (0.5, 0.5, 0.8), "curious": (0.55, 0.5, 0.85), "calm": (0.35, 0.55, 0.75),
    "serious": (0.3, 0.6, 0.7), "considerate": (0.3, 0.55, 0.75),
}


def _patch_tokenizer_dtype() -> None:
    """librosa 1.0 resamples to float64; the model's tokenizer expects float32."""
    try:
        import torch
        from chatterbox.models.s3tokenizer import s3tokenizer as s3

        if getattr(s3.S3Tokenizer, "_ttg_patched", False):
            return
        orig = s3.S3Tokenizer.log_mel_spectrogram

        def fixed(self, audio, *a, **k):
            if isinstance(audio, np.ndarray):
                audio = audio.astype(np.float32)
            elif torch.is_tensor(audio):
                audio = audio.float()
            return orig(self, audio, *a, **k)

        s3.S3Tokenizer.log_mel_spectrogram = fixed
        s3.S3Tokenizer._ttg_patched = True

        # the reference pipeline (librosa.resample / loudness norm) hands float64 to float32 networks
        import chatterbox.tts_turbo as tt

        real = tt.librosa

        class _Librosa32:
            def __getattr__(self, name):
                return getattr(real, name)

            def load(self, *a, **k):
                y, sr = real.load(*a, **k)
                return np.asarray(y, dtype=np.float32), sr

            def resample(self, *a, **k):
                return np.asarray(real.resample(*a, **k), dtype=np.float32)

        tt.librosa = _Librosa32()
        orig_norm = tt.ChatterboxTurboTTS.norm_loudness

        def norm32(self, wav, sr):
            return np.asarray(orig_norm(self, wav, sr), dtype=np.float32)

        tt.ChatterboxTurboTTS.norm_loudness = norm32
    except Exception as exc:  # noqa: BLE001
        log.warning("tokenizer dtype patch skipped: %s", exc)


from .edge_voice import _ctx  # noqa: E402
from .sfx import available as sfx_available  # noqa: E402


class ChatterboxSpeaker(EdgeSpeaker):
    expressive = True

    # variants: "turbo" (fast, performs [laugh]/[sigh] tags), "full" (slower, follows the reference more closely:
    # cfg_weight 0.3), "mtl" (multilingual; language "ar" speaks English with an Arabic accent). Picked by voice id:
    # "haddan_own_c" = turbo, "haddan_own_c|full", "haddan_own_c|ar" (= mtl + Arabic), "haddan_own_c|mtl" (mtl, English)
    VARIANTS = ("turbo", "full", "mtl")

    def __init__(self, ref: str | None = None, device: str | None = None, variant: str | None = None, language: str | None = None) -> None:
        super().__init__(voice="en-US-GuyNeural", device=device)
        self.engine = "chatterbox"
        self.voice = str(ref or os.getenv("TTS_REF") or DEFAULT_REF)
        self.variant = (variant or os.getenv("TTS_VARIANT", "turbo")).lower()
        self.language = (language or os.getenv("TTS_LANG", "en")).lower()
        self.cfg_weight = float(os.getenv("TTS_CFG", "0.3"))
        self._models: dict[str, object] = {}
        self._model_lock = threading.Lock()
        self._gpu_lock = threading.Lock()
        self.model_sr = 24000
        self.apply_voice_id(Path(self.voice).stem + ("" if self.variant == "turbo" else "|" + (self.language if self.variant == "mtl" and self.language != "en" else self.variant)))
        log.info("Chatterbox voice selected: reference=%s variant=%s language=%s", Path(self.voice).name, self.variant, self.language)

    def apply_voice_id(self, voice_id: str) -> None:
        """'haddan_own_c', 'haddan_own_c|full', 'haddan_own_c|ar', 'haddan_own_c|mtl' -> reference, variant, language."""
        name, _, opt = voice_id.partition("|")
        ref = Path("app/voice/ref") / (name if name.endswith(".wav") else f"{name}.wav")
        if ref.exists():
            self.voice = str(ref)
        opt = opt.lower().strip()
        if opt in ("", "turbo"):
            self.variant, self.language = "turbo", "en"
        elif opt == "full":
            self.variant, self.language = "full", "en"
        elif opt == "mtl":
            self.variant, self.language = "mtl", "en"
        else:
            self.variant, self.language = "mtl", opt          # a language code: multilingual model, that accent
        self.expressive = self.variant == "turbo" or sfx_available()
        with self._cache_lock:
            self._cache.clear()

    @property
    def performs_tags(self) -> bool:
        return self.variant == "turbo"

    # ---- model -----------------------------------------------------------------
    def _load(self, variant: str | None = None):
        variant = variant or self.variant
        with self._model_lock:
            if variant not in self._models:
                t0 = time.time()
                _patch_tokenizer_dtype()
                if variant == "full":
                    from chatterbox.tts import ChatterboxTTS as M
                elif variant == "mtl":
                    from chatterbox.mtl_tts import ChatterboxMultilingualTTS as M
                else:
                    from chatterbox.tts_turbo import ChatterboxTurboTTS as M
                self._models[variant] = M.from_pretrained(device="cuda")
                self.model_sr = int(getattr(self._models[variant], "sr", 24000))
                log.info("Chatterbox %s loaded on cuda in %.0fs (sr %d)", variant, time.time() - t0, self.model_sr)
        return self._models[variant]

    def warm(self) -> None:
        threading.Thread(target=self._load, daemon=True).start()

    @staticmethod
    def emotion_for(text: str, mood: str) -> float:
        """Exaggeration for one sentence: the mood sets the floor, the words move it. A question lifts, a real move
        lifts a lot, the risk line and asides settle. Turbo ignores this; the full and multilingual models use it."""
        from .human import ASIDE_RE, EXCITE_RE, POINT_RE, RISK_RE

        # kept narrow on purpose: a wide swing in exaggeration changes the character of the voice from line to line,
        # which the host hears as "not my voice". The words move it a little; the timbre stays his.
        e = 0.5
        if EXCITE_RE.search(text) or text.strip().endswith("?"):
            e += 0.06
        if RISK_RE.search(text) or ASIDE_RE.search(text):
            e -= 0.06
        return float(max(0.42, min(0.58, e)))

    def _synth_one(self, text: str) -> np.ndarray:
        from scipy.signal import resample_poly

        model = self._load()
        exag, cfg, temp = MOOD_PARAMS.get(self.mood, MOOD_PARAMS["teach"])
        exag = self.emotion_for(text, self.mood)
        # the producer (the line being spoken now) goes first; a prefetch of a later line waits its turn
        if not getattr(_ctx, "urgent", False):
            t_w = time.time()
            while getattr(self, "_urgent_count", 0) > 0 and time.time() - t_w < 30:
                time.sleep(0.05)
        t0 = time.time()
        if self.variant != "turbo":
            from .tags import strip as _strip
            text = _strip(text) or text                       # only Turbo performs bracket tags
        with self._gpu_lock:
            if self.variant == "full":
                wav = model.generate(text, audio_prompt_path=self.voice, exaggeration=exag, cfg_weight=self.cfg_weight, temperature=temp)
            elif self.variant == "mtl":
                wav = model.generate(text, language_id=self.language, audio_prompt_path=self.voice, exaggeration=exag, cfg_weight=self.cfg_weight, temperature=temp)
            else:
                wav = model.generate(text, audio_prompt_path=self.voice, temperature=temp)   # Turbo ignores exaggeration/cfg (and warns per call)
        a = wav.squeeze().detach().cpu().numpy().astype(np.float32)
        dt = time.time() - t0
        secs = a.size / self.model_sr
        if secs > 0.8:                                   # running estimate of synthesis speed (seconds of work per second of audio)
            self.rtf = 0.75 * getattr(self, "rtf", 0.8) + 0.25 * (dt / secs)
        if dt > 0.5:
            log.info("chatterbox synth: %.1fs audio in %.1fs (x%.2f)", a.size / self.model_sr, dt, dt / max(a.size / self.model_sr, 0.1))
        if self.model_sr != self.out_rate:
            from math import gcd

            g = gcd(self.out_rate, self.model_sr)
            a = resample_poly(a, self.out_rate // g, self.model_sr // g).astype(np.float32)
        return a

    # ---- EdgeSpeaker contract ------------------------------------------------------
    def synth_many(self, sentences: list[str]) -> list[np.ndarray]:
        """Sequential GPU synthesis with the same cache/in-flight semantics as the online voice."""
        if getattr(self, "_cache_mood", None) != self.mood:
            with self._cache_lock:
                self._cache.clear()
            self._cache_mood = self.mood
        for s in sentences:
            with self._cache_lock:
                if s in self._cache:
                    continue
                if s in self._inflight:
                    pending = True
                else:
                    self._inflight.add(s)
                    pending = False
            if pending:
                deadline = time.time() + FETCH_TIMEOUT_S * 3
                while time.time() < deadline:
                    with self._cache_lock:
                        if s in self._cache or s not in self._inflight:
                            break
                    time.sleep(0.05)
                continue
            try:
                a = self._synth_one(s)
                with self._cache_lock:
                    self._cache[s] = a
                    while len(self._cache) > 200:
                        self._cache.popitem(last=False)
            except Exception as exc:  # noqa: BLE001
                log.warning("chatterbox failed for %r: %s", s[:40], exc)
            finally:
                with self._cache_lock:
                    self._inflight.discard(s)
        with self._cache_lock:
            return [self._cache.get(s, np.zeros(0, dtype=np.float32)) for s in sentences]
