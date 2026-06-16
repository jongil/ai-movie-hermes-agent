"""QLoRA peak-VRAM probe for gemma4-12b on 16GB.
Loads the model in 4-bit, attaches LoRA, runs ONE train step at a given
sequence length, and reports peak CUDA memory. Content is irrelevant to
VRAM, so we use random token ids of the target length (batch=1).
Usage: python qlora_vram_probe.py <seq_len>   (e.g. 4096, 8192)
"""
import os
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import sys, torch, gc
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

MODEL = "unsloth/gemma-4-12b-it"
seq_len = int(sys.argv[1]) if len(sys.argv) > 1 else 8192

torch.cuda.reset_peak_memory_stats()
bnb = BitsAndBytesConfig(
    load_in_4bit=True, bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
)
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(
    MODEL, quantization_config=bnb, device_map="cuda", dtype=torch.bfloat16,
    attn_implementation="eager",
)
# Text-only: free the vision tower (대본 writing never uses images)
freed = []
for parent in [model, getattr(model, "model", None)]:
    if parent is None:
        continue
    for name in list(dict(parent.named_children()).keys()):
        if any(k in name.lower() for k in ("vision", "multi_modal", "mm_", "image")):
            try:
                delattr(parent, name); freed.append(name)
            except Exception:
                pass
gc.collect(); torch.cuda.empty_cache()
print("freed_vision_modules=", freed)
model.gradient_checkpointing_enable()
model = prepare_model_for_kbit_training(model)
lora = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
)
model = get_peft_model(model, lora)
model.train()

after_load = torch.cuda.max_memory_allocated() / 1e9
print(f"after_load_GB= {after_load:.2f}")

vocab = model.config.text_config.vocab_size if hasattr(model.config, "text_config") else model.config.vocab_size
ids = torch.randint(0, vocab, (1, seq_len), device="cuda")
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4)

for step in range(2):
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
