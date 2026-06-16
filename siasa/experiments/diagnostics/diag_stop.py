"""Step1 진단: v1 어댑터가 EOS를 뱉는가 / 클로징 직후 멈추는가 / 학습데이터에 EOS가 있는가."""
import os, json, re
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
from unsloth import FastModel
import torch

BASE = "/home/gdash86/project/ai-movie-hermes-agent"
LORA = f"{BASE}/siasa_lora"
CLOSE = "복잡한 세상, 제대로 읽어갑시다"
SYSTEM = ("당신은 시사 베테랑 채널의 임한수 작가입니다. 주어진 주제로 5070 시니어 대상 시사·경제 "
          "유튜브 내레이션 대본을 작성합니다. 팩트 기반 분석, 후킹 도입, 쉬운 말 변환, 한글 숫자 표기, "
          "마지막 채널 멘트를 지킵니다.")

model, tok = FastModel.from_pretrained(LORA, max_seq_length=8192, load_in_4bit=True)
FastModel.for_inference(model)
tk = getattr(tok, "tokenizer", tok)

# --- A. 토크나이저 EOS/종료 토큰 식별 ---
print("=== A. EOS/종료 토큰 ===")
print("eos_token=", repr(tk.eos_token), "id=", tk.eos_token_id)
print("pad_token=", repr(tk.pad_token), "id=", tk.pad_token_id)
for t in ["<end_of_turn>", "<|turn>", "<eos>", "<end_of_text>"]:
    try:
        ids = tk.convert_tokens_to_ids(t)
        print(f"  {t!r} -> id {ids}")
    except Exception as e:
        print(f"  {t!r} -> {e}")

# --- B. 학습데이터 1개를 chat_template로 토큰화 → assistant 끝에 EOS가 붙는가 ---
print("\n=== B. 학습데이터 EOS 부착 검사 ===")
ex = json.loads(open(f"{BASE}/train.jsonl", encoding="utf-8").readline())
rendered = tk.apply_chat_template(ex["messages"], tokenize=False)
print("rendered tail (마지막 120자):", repr(rendered[-120:]))
ids = tk.apply_chat_template(ex["messages"], tokenize=True)
print("마지막 토큰 8개 id:", ids[-8:])
print("마지막 토큰 8개 decode:", [tk.decode([i]) for i in ids[-8:]])
print("eos_id가 마지막부근에 있나:", tk.eos_token_id in ids[-5:])

# --- C. 생성: min_new_tokens 없이, EOS 정지 허용 ---
print("\n=== C. 생성 (min_new_tokens 없음) ===")
topic = "원달러 환율이 천사백오십원을 넘었습니다"
msgs = [{"role":"system","content":SYSTEM},
        {"role":"user","content":f"주제: {topic}\n\n이 주제로 시사베테랑 대본을 작성해 주세요."}]
prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
inp = tk(prompt, return_tensors="pt").to("cuda")
n_in = inp["input_ids"].shape[1]
MAXNEW = 6000
out = model.generate(**inp, max_new_tokens=MAXNEW, do_sample=True, temperature=0.8, top_p=0.9,
                     repetition_penalty=1.1, eos_token_id=tk.eos_token_id, pad_token_id=tk.pad_token_id)
gen_ids = out[0][n_in:]
n_gen = gen_ids.shape[0]
hit_eos = (n_gen < MAXNEW)  # max 못 채우고 끝나면 EOS로 정지
text = tk.decode(gen_ids, skip_special_tokens=True).strip()
print(f"생성 토큰수={n_gen} / max={MAXNEW} → {'EOS 정지' if hit_eos else 'MAX 도달(정지 실패)'}")
print(f"len_chars={len(text)} closing={text.count(CLOSE)}")
# 클로징 직후 정지 여부
if CLOSE in text:
    after = text.split(CLOSE, 1)[1]
    # 클로징 뒤에 보통 '나 임한수…' 한 문장 정도는 정상. 그 이상 길면 미정지.
    print(f"클로징 이후 잔여 길이={len(after)}자")
    print("클로징 이후 잔여(앞 200자):", repr(after[:200]))
print("=== TAIL 300 ===")
print(text[-300:])
open(f"{BASE}/diag_out.txt","w",encoding="utf-8").write(text)
