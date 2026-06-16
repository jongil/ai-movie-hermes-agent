"""Step2: gen-config 다중시드 스윕 — 안정 생성(클로징 도달+EOS 정지+비퇴화) config 탐색."""
import os, re, sys
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
from unsloth import FastModel
import torch

BASE = "/home/gdash86/project/ai-movie-hermes-agent"
LORA = f"{BASE}/siasa_lora"
CLOSE = "복잡한 세상, 제대로 읽어갑시다"
EOS = 106  # gemma4 <turn|>
SYSTEM = ("당신은 시사 베테랑 채널의 임한수 작가입니다. 주어진 주제로 5070 시니어 대상 시사·경제 "
          "유튜브 내레이션 대본을 작성합니다. 팩트 기반 분석, 후킹 도입, 쉬운 말 변환, 한글 숫자 표기, "
          "마지막 채널 멘트를 지킵니다.")
TOPIC = "원달러 환율이 천사백오십원을 넘었습니다"

model, tok = FastModel.from_pretrained(LORA, max_seq_length=8192, load_in_4bit=True)
FastModel.for_inference(model)
tk = getattr(tok, "tokenizer", tok)

print("=== 기본값 버그 확인 ===")
print("model.generation_config.eos_token_id =", model.generation_config.eos_token_id, "(정답=106 <turn|>)")
print("tk.eos_token_id =", tk.eos_token_id, flush=True)

msgs = [{"role":"system","content":SYSTEM},
        {"role":"user","content":f"주제: {TOPIC}\n\n이 주제로 시사베테랑 대본을 작성해 주세요."}]
prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
inp = tk(prompt, return_tensors="pt").to("cuda")
n_in = inp["input_ids"].shape[1]
MAXNEW = 4500

def degenerate(text):
    """연속 동일 줄 3회+ 또는 동일 40자 윈도 4회+ = 퇴화."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    run = 1
    for i in range(1, len(lines)):
        run = run + 1 if lines[i] == lines[i-1] else 1
        if run >= 3: return True
    for i in range(0, max(0,len(text)-40), 20):
        w = text[i:i+40]
        if len(w) == 40 and text.count(w) >= 4: return True
    return False

CONFIGS = [
    ("A rep1.2/ng6/t0.7",  dict(repetition_penalty=1.2,  no_repeat_ngram_size=6, temperature=0.7, top_p=0.9)),
    ("B rep1.3/ng8/t0.7",  dict(repetition_penalty=1.3,  no_repeat_ngram_size=8, temperature=0.7, top_p=0.9)),
    ("C rep1.25/ng6/t0.8", dict(repetition_penalty=1.25, no_repeat_ngram_size=6, temperature=0.8, top_p=0.92)),
]
SEEDS = [11, 42, 77]

print("\n=== 스윕 (eos=106, min_new_tokens 없음, max=%d) ===" % MAXNEW, flush=True)
print(f"{'config':22} {'seed':>4} {'tok':>5} {'stop':>5} {'chars':>6} {'close':>5} {'resid':>6} {'degen':>5}")
summary = {}
for name, gc in CONFIGS:
    good = 0
    for sd in SEEDS:
        torch.manual_seed(sd)
        out = model.generate(**inp, max_new_tokens=MAXNEW, do_sample=True,
                             eos_token_id=EOS, pad_token_id=tk.pad_token_id, **gc)
        g = out[0][n_in:]
        n = g.shape[0]
        stopped = n < MAXNEW
        text = tk.decode(g, skip_special_tokens=True).strip()
        nclose = text.count(CLOSE)
        resid = len(text.split(CLOSE,1)[1]) if CLOSE in text else -1
        deg = degenerate(text)
        ok = stopped and nclose >= 1 and not deg and 3000 <= len(text) <= 7000
        good += ok
        print(f"{name:22} {sd:>4} {n:>5} {str(stopped):>5} {len(text):>6} {nclose:>5} {resid:>6} {str(deg):>5}"
              + ("  <= OK" if ok else ""), flush=True)
    summary[name] = good
print("\n=== 요약 (OK = stop&close&non-degen&3-7K) ===")
for name, g in sorted(summary.items(), key=lambda x:-x[1]):
    print(f"  {name:22}: {g}/{len(SEEDS)} OK")
