"""Unsloth QLoRA peak-VRAM probe for gemma4-12b on 16GB.
Usage: python unsloth_vram_probe.py <seq_len>
"""
import os
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import sys
from unsloth import FastModel  # must import before torch/transformers
import torch

MODEL = "unsloth/gemma-4-12b-it"
seq_len = int(sys.argv[1]) if len(sys.argv) > 1 else 8192

torch.cuda.reset_peak_memory_stats()
model, tok = FastModel.from_pretrained(
    model_name=MODEL,
    max_seq_length=seq_len,
    load_in_4bit=True,
    full_finetuning=False,
)
after_load = torch.cuda.max_memory_allocated() / 1e9
print(f"after_load_GB= {after_load:.2f}")

model = FastModel.get_peft_model(
    model,
    r=16, lora_alpha=32, lora_dropout=0, bias="none",
    finetune_vision_layers=False,
    finetune_language_layers=True,
    finetune_attention_modules=True,
    finetune_mlp_modules=True,
    random_state=42,
)
model.train()

vocab = getattr(model.config, "vocab_size", None) or model.config.text_config.vocab_size
ids = torch.randint(0, vocab, (1, seq_len), device="cuda")
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4)
for _ in range(2):
    out = model(input_ids=ids, labels=ids)
    out.loss.backward()
    opt.step(); opt.zero_grad()

peak = torch.cuda.max_memory_allocated() / 1e9
total = torch.cuda.get_device_properties(0).total_memory / 1e9
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad) / 1e6
print(f"seq_len= {seq_len}")
print(f"trainable_params_M= {trainable:.1f}")
print(f"PEAK_VRAM_GB= {peak:.2f}  / TOTAL_GB= {total:.1f}")
print("FITS_16GB=", peak < total)
