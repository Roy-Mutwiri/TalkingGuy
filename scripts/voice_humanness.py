"""Humanness meter for the stream voice, trained on the Kaggle "Speech dataset of human and
AI-generated voices" (kambingbersayaphitam). Needs your Kaggle credentials once:

    1. kaggle.com -> Settings -> API -> Create New Token  (downloads kaggle.json)
    2. put it at %USERPROFILE%\\.kaggle\\kaggle.json
    3. .venv\\Scripts\\pip install kaggle
    4. .venv\\Scripts\\python scripts\\voice_humanness.py --download
    5. .venv\\Scripts\\python scripts\\voice_humanness.py --train
    6. .venv\\Scripts\\python scripts\\voice_humanness.py --score data_cache\\mix.wav

The classifier (log-mel statistics + logistic regression, no GPU needed) gives a 0..1 "sounds
human" score. Use it to A/B the mic chain, breaths and prosody settings: higher is better.
It is a tuning tool, not a guarantee against any particular detector.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

DATA = Path("data_cache/datasets/kaggle_voices")
MODEL = Path("data_cache/humanness_model.json")


def features(path: Path, sr: int = 16000) -> np.ndarray:
    import soundfile as sf
    from scipy.signal import resample_poly, stft

    x, r = sf.read(str(path), dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    if r != sr:
        g = np.gcd(int(r), sr)
        x = resample_poly(x, sr // g, int(r) // g).astype(np.float32)
    x = x[: sr * 20]
    f, t, Z = stft(x, fs=sr, nperseg=512, noverlap=384)
    mag = np.abs(Z) + 1e-8
    # 40 mel-ish bands via triangular filters on a log-spaced grid
    edges = np.geomspace(60, sr / 2, 42)
    bands = np.stack([mag[(f >= edges[i]) & (f < edges[i + 2])].mean(axis=0) if ((f >= edges[i]) & (f < edges[i + 2])).any() else np.zeros(mag.shape[1]) for i in range(40)])
    logm = np.log(bands + 1e-6)
    feats = np.concatenate([logm.mean(axis=1), logm.std(axis=1), np.diff(logm, axis=1).std(axis=1),
                            [np.log(np.abs(x).max() + 1e-6), np.log(np.sqrt((x ** 2).mean()) + 1e-6), (np.abs(np.diff(np.sign(x))) > 0).mean()]])
    return feats.astype(np.float64)


def collect() -> tuple[list[Path], list[int]]:
    files, labels = [], []
    for p in DATA.rglob("*"):
        if p.suffix.lower() not in (".wav", ".mp3", ".flac", ".ogg", ".m4a"):
            continue
        low = str(p).lower()
        if "human" in low or "real" in low:
            files.append(p); labels.append(1)
        elif "ai" in low or "fake" in low or "synth" in low or "tts" in low:
            files.append(p); labels.append(0)
    return files, labels


def train() -> None:
    files, labels = collect()
    if not files:
        sys.exit(f"no audio found under {DATA}; run --download first")
    X = np.stack([features(f) for f in files]); y = np.array(labels, dtype=np.float64)
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-6
    Xn = (X - mu) / sd
    w = np.zeros(Xn.shape[1]); b = 0.0
    for _ in range(2000):   # logistic regression, gradient descent with L2
        z = Xn @ w + b; p = 1 / (1 + np.exp(-z))
        gw = Xn.T @ (p - y) / len(y) + 1e-3 * w; gb = (p - y).mean()
        w -= 0.3 * gw; b -= 0.3 * gb
    acc = ((1 / (1 + np.exp(-(Xn @ w + b))) > 0.5) == (y > 0.5)).mean()
    MODEL.write_text(json.dumps({"w": w.tolist(), "b": b, "mu": mu.tolist(), "sd": sd.tolist(), "train_acc": float(acc), "n": len(y)}))
    print(f"trained on {len(y)} clips, train accuracy {acc:.2%} -> {MODEL}")


def score(path: Path) -> float:
    m = json.loads(MODEL.read_text())
    x = (features(path) - np.array(m["mu"])) / np.array(m["sd"])
    return float(1 / (1 + np.exp(-(x @ np.array(m["w"]) + m["b"]))))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--score", nargs="*")
    a = ap.parse_args()
    if a.download:
        import subprocess
        DATA.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "kaggle", "datasets", "download", "-d", "kambingbersayaphitam/speech-dataset-of-human-and-ai-generated-voices", "-p", str(DATA), "--unzip"], check=True)
    if a.train:
        train()
    for f in a.score or []:
        print(f"{f}: sounds-human score {score(Path(f)):.2f}")
