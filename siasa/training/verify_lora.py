"""파인튜닝된 시사베테랑 LoRA 검증 — 새 주제로 단일패스 대본 생성."""
import os
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
import sys, re
from unsloth import FastModel
import torch

BASE = os.environ.get("HERMES_DIR", "/home/gdash86/project/ai-movie-hermes-agent")
LORA = f"{BASE}/siasa_lora"
SYSTEM = (
    "당신은 시사 베테랑 채널의 임한수 작가입니다. "
    "주어진 주제로 5070 시니어 대상 시사·경제 유튜브 내레이션 대본을 작성합니다. "
    "팩트 기반 분석, 후킹 도입, 쉬운 말 변환, 한글 숫자 표기, 마지막 채널 멘트를 지킵니다."
)
topic = sys.argv[1] if len(sys.argv) > 1 else "원달러 환율이 천사백오십원을 넘었습니다"

model, tok = FastModel.from_pretrained(LORA, max_seq_length=8192, load_in_4bit=True)
FastModel.for_inference(model)

msgs = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": f"주제: {topic}\n\n이 주제로 시사베테랑 대본을 작성해 주세요."},
]
tk = getattr(tok, "tokenizer", tok)  # gemma4 processor → 내부 텍스트 토크나이저
prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
inputs = tk(prompt, return_tensors="pt").to("cuda")
n_in = inputs["input_ids"].shape[1]
out = model.generate(**inputs, max_new_tokens=5000, min_new_tokens=2800, temperature=0.8, top_p=0.9, do_sample=True,
                     repetition_penalty=1.15, no_repeat_ngram_size=10)
text = tk.decode(out[0][n_in:], skip_special_tokens=True).strip()

open(f"{BASE}/verify_out.txt", "w", encoding="utf-8").write(text)
print("=== AUTO-CHECK ===")
print("len_chars=", len(text))
print("closing=", text.count("복잡한 세상, 제대로 읽어갑시다"))
print("imhansu=", text.count("나 임한수"))
print("md_headers=", len(re.findall(r"(?m)^#", text)))
print("arabic=", len(re.findall(r"[0-9]", text)))
print("paren=", len(re.findall(r"[()]", text)))
print("=== HEAD ===")
print(text[:700])
print("=== TAIL ===")
print(text[-300:])
