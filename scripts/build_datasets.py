"""Build the lexicons the host uses from the two Hugging Face datasets:

  HumanLLMs/Human-Like-DPO-Dataset  -> app/brain/style_examples.json  (short human-like replies, emoji stripped,
                                       used as style exemplars in the chat responder prompt)
  aborasheed/Global-Human-Names     -> data_cache/names.json            (first names from many countries, used to
                                       say viewers' names properly and ignore handle junk)

    .venv\\Scripts\\python scripts\\build_datasets.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.chat.names import strip_for_speech  # noqa: E402


def build_style_examples(n: int = 40) -> int:
    from huggingface_hub import hf_hub_download

    p = hf_hub_download("HumanLLMs/Human-Like-DPO-Dataset", "data.json", repo_type="dataset", local_dir="data_cache/datasets/human_like_dpo")
    rows = json.load(open(p, encoding="utf-8"))
    rnd = random.Random(11)
    rnd.shuffle(rows)
    picked = []
    for r in rows:
        chosen = strip_for_speech(r["chosen"]).strip()
        prompt = strip_for_speech(r["prompt"]).strip()
        if 40 <= len(chosen) <= 260 and 10 <= len(prompt) <= 160 and "\n" not in chosen and "http" not in chosen:
            picked.append({"prompt": re.sub(r"\s+", " ", prompt), "reply": re.sub(r"\s+", " ", chosen)})
        if len(picked) >= n:
            break
    out = Path("app/brain/style_examples.json")
    out.write_text(json.dumps(picked, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(picked)


def build_names() -> int:
    import pandas as pd
    from huggingface_hub import hf_hub_download

    frames = []
    for i in range(2):
        f = hf_hub_download("aborasheed/Global-Human-Names", f"data/train-0000{i}-of-00002.parquet", repo_type="dataset", local_dir="data_cache/datasets/names")
        frames.append(pd.read_parquet(f))
    df = pd.concat(frames)
    cols = [c for c in df.columns if any(k in c.lower() for k in ("first", "given", "name"))]
    col = cols[0] if cols else df.columns[0]
    names: set[str] = set()
    for v in df[col].dropna().astype(str):
        w = v.strip().split()[0] if v.strip() else ""
        w = re.sub(r"[^A-Za-z]", "", w)
        if 2 <= len(w) <= 14:
            names.add(w.lower())
    Path("data_cache").mkdir(exist_ok=True)
    Path("data_cache/names.json").write_text(json.dumps(sorted(names)), encoding="utf-8")
    return len(names)


if __name__ == "__main__":
    print("style examples:", build_style_examples())
    print("first names:", build_names())
