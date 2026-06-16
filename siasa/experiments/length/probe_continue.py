"""이어쓰기 프로브: assistant 턴 연속생성이 본문을 실제로 확장하는지 pass별 측정."""
import os, sys
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
sys.path.insert(0, "/home/gdash86/project/ai-movie-hermes-agent")
from unsloth import FastModel
import torch
from script_guard import strip_closing_tail, ensure_closing, CLOSING

BASE = "/home/gdash86/project/ai-movie-hermes-agent"
LORA = f"{BASE}/siasa_lora_e6"
EOS = 106
SYSTEM = ("당신은 시사 베테랑 채널의 임한수 작가입니다. 주어진 주제로 5070 시니어 대상 시사·경제 "
          "유튜브 내레이션 대본을 작성합니다. 팩트 기반 분석, 후킹 도입, 쉬운 말 변환, 한글 숫자 표기, "
          "마지막 채널 멘트를 지킵니다.")
TOPIC = "원달러 환율이 천사백오십원을 넘었습니다"
GC = dict(repetition_penalty=1.3, no_repeat_ngram_size=8, temperature=0.7, top_p=0.9)

model, tok = FastModel.from_pretrained(LORA, max_seq_length=8192, load_in_4bit=True)
FastModel.for_inference(model)
tk = getattr(tok, "tokenizer", tok)

msgs = [{"role":"system","content":SYSTEM},
        {"role":"user","content":f"주제: {TOPIC}\n\n이 주제로 시사베테랑 대본을 작성해 주세요."}]
head = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

def gen(prompt_text, max_new, seed):
    torch.manual_seed(seed)
    inp = tk(prompt_text, return_tensors="pt").to("cuda")
    n_in = inp["input_ids"].shape[1]
    out = model.generate(**inp, max_new_tokens=max_new, do_sample=True,
                        eos_token_id=EOS, pad_token_id=tk.pad_token_id, **GC)
    return tk.decode(out[0][n_in:], skip_special_tokens=True).strip()

# Pass 1
raw = gen(head, 2600, 11)
body = strip_closing_tail(raw)
print(f"PASS1 body={len(body)} (raw_closing={raw.count(CLOSING)})", flush=True)

# 이어쓰기 패스
stall = 0
for i in range(2, 7):
    cont_prompt = head + body
    cont = gen(cont_prompt, 2000, 10 + i)
    new = strip_closing_tail(cont)
    added = len(new)
    print(f"PASS{i} added={added} re_closed={CLOSING in cont}", flush=True)
    if added < 150:
        stall += 1
        if stall >= 2:
            print("STALL ×2 → 중단"); break
    else:
        stall = 0
        body = (body + "\n" + new).strip()
    if len(body) >= 4500:
        print("목표 도달"); break

final = ensure_closing(body)
print(f"\nFINAL body={len(body)} final_total={len(final)} closing={final.count(CLOSING)}", flush=True)
open(f"{BASE}/continue_sample.txt","w",encoding="utf-8").write(final)
