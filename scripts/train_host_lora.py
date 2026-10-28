"""Fine-tuning smoke pipeline for a local host model (SFT, then optional DPO) with Hugging Face TRL.

This is the pipeline the streamer pack's README describes. The starter set (32 train / 8 validation
examples) is only enough to prove the plumbing; collect 2,000-5,000 reviewed moments before trusting
an adapter. Rejected preference answers are never used as SFT targets.

    pip install "trl>=0.12" peft datasets accelerate bitsandbytes transformers
    python scripts/train_host_lora.py --base Qwen/Qwen2.5-3B-Instruct --out data_cache/host_lora
    python scripts/train_host_lora.py --dpo --out data_cache/host_lora_dpo        # after SFT

A 16 GB GPU fits a 3B model in 4-bit QLoRA. The result is an adapter you can serve with vLLM/llama.cpp
and point TEMPLATE/ANTHROPIC-free replies at later; the live runtime still routes through the host policy.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / "training" / "streamer_pack" / "TradeFix_Streamer_Training_Starter"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--out", default="data_cache/host_lora")
    ap.add_argument("--dpo", action="store_true", help="run DPO on the preference pairs (loads --adapter if given)")
    ap.add_argument("--adapter", default="", help="SFT adapter to start DPO from")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=2048)
    a = ap.parse_args()

    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from trl import DPOConfig, DPOTrainer, SFTConfig, SFTTrainer
    except ImportError as exc:
        sys.exit(f"missing training deps ({exc}); run: pip install trl peft datasets accelerate bitsandbytes transformers")

    if not PACK.exists():
        sys.exit(f"pack not found at {PACK}")
    tok = AutoTokenizer.from_pretrained(a.base)
    tok.pad_token = tok.pad_token or tok.eos_token
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_quant_type="nf4")
    model = AutoModelForCausalLM.from_pretrained(a.base, quantization_config=quant, device_map="auto")
    lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules="all-linear", task_type="CAUSAL_LM")

    if not a.dpo:
        ds = load_dataset("json", data_files={"train": str(PACK / "sft_train.jsonl"), "validation": str(PACK / "sft_validation.jsonl")})
        cfg = SFTConfig(output_dir=a.out, num_train_epochs=a.epochs, learning_rate=a.lr, per_device_train_batch_size=2, gradient_accumulation_steps=4,
                        max_length=a.max_len, logging_steps=5, eval_strategy="epoch", save_strategy="epoch", bf16=True, report_to=[])
        trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds["train"], eval_dataset=ds["validation"], processing_class=tok, peft_config=lora)
        trainer.train()
        trainer.save_model(a.out)
        print("SFT adapter saved to", a.out, "| eval:", trainer.evaluate())
        return

    if a.adapter:
        model = PeftModel.from_pretrained(model, a.adapter, is_trainable=True)
    ds = load_dataset("json", data_files={"train": str(PACK / "preference_train.jsonl"), "validation": str(PACK / "preference_validation.jsonl")})
    cfg = DPOConfig(output_dir=a.out, num_train_epochs=a.epochs, learning_rate=5e-6, per_device_train_batch_size=1, gradient_accumulation_steps=4,
                    max_length=a.max_len, beta=0.1, logging_steps=2, eval_strategy="epoch", save_strategy="epoch", bf16=True, report_to=[])
    trainer = DPOTrainer(model=model, args=cfg, train_dataset=ds["train"], eval_dataset=ds["validation"], processing_class=tok, peft_config=None if a.adapter else lora)
    trainer.train()
    trainer.save_model(a.out)
    print("DPO adapter saved to", a.out, "| eval:", trainer.evaluate())


if __name__ == "__main__":
    main()
