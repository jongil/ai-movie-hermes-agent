"""writer 로드→짧은 생성→종료. 프로세스 종료가 VRAM 회수하는지 검증용."""
import os, sys
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
sys.path.insert(0, "/home/gdash86/project/ai-movie-hermes-agent")
from unsloth import FastModel
import torch
m, tok = FastModel.from_pretrained("/home/gdash86/project/ai-movie-hermes-agent/siasa_lora_e6",
                                   max_seq_length=8192, load_in_4bit=True)
FastModel.for_inference(m)
tk = getattr(tok, "tokenizer", tok)
print("로드 후 VRAM(MiB):", round(torch.cuda.memory_allocated()/1024**2))
inp = tk("안녕하세요", return_tensors="pt").to("cuda")
m.generate(**inp, max_new_tokens=20, eos_token_id=106)
print("생성 완료, 프로세스 종료(VRAM은 OS가 회수)")
