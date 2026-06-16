"""LoRA를 base gemma4에 merge → 16bit safetensors (Ollama import용)."""
import os
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
from unsloth import FastModel

BASE = "/home/gdash86/project/ai-movie-hermes-agent"
LORA = f"{BASE}/siasa_lora_e6"
MERGED = f"{BASE}/siasa_merged_16bit"

model, tok = FastModel.from_pretrained(LORA, max_seq_length=8192, load_in_4bit=True)
print("로드 완료. merge 시도...", flush=True)

# 1순위: unsloth save_pretrained_merged (4bit→16bit 디퀀트+머지)
if hasattr(model, "save_pretrained_merged"):
    print("경로=save_pretrained_merged(merged_16bit)", flush=True)
    model.save_pretrained_merged(MERGED, tok, save_method="merged_16bit")
else:
    print("경로=peft merge_and_unload 폴백", flush=True)
    merged = model.merge_and_unload()
    merged.save_pretrained(MERGED, safe_serialization=True)
    tok.save_pretrained(MERGED)

print("MERGE_DONE:", MERGED, flush=True)
import glob
for f in sorted(glob.glob(f"{MERGED}/*")):
    print("  ", os.path.basename(f))
