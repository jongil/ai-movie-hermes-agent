"""사실 주입 프로브: 명시 지시+낮은 temp로 헤드라인 수치가 살아남는가."""
import os, sys, re
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
sys.path.insert(0, "/home/gdash86/project/ai-movie-hermes-agent")
from unsloth import FastModel
import torch
from siasa_writer import SYSTEM, build_user_prompt, EOS_ID
from script_guard import ensure_closing

BASE = "/home/gdash86/project/ai-movie-hermes-agent"
LORA = f"{BASE}/siasa_lora_e6"
TOPIC = "원달러 환율이 천사백오십원을 넘었습니다"
TARGET = "천사백오십원"   # 살아남아야 할 헤드라인 수치

model, tok = FastModel.from_pretrained(LORA, max_seq_length=8192, load_in_4bit=True)
FastModel.for_inference(model)
tk = getattr(tok, "tokenizer", tok)

def won_values(t):
    """한글수치+원 토큰 추출, 공백제거 정규화, 접미(대/선) 제거."""
    raw = re.findall(r"[일이삼사오육칠팔구십백천만영\s]{2,}원", t)
    norm = set()
    for r in raw:
        v = re.sub(r"\s+", "", r)
        norm.add(v)
    return norm

def carry(t):
    flat = re.sub(r"\s+", "", t)
    return TARGET in flat   # 공백 정규화 후 부분일치(접미 허용)

def gen(user, seed, temp):
    torch.manual_seed(seed)
    p = tok.apply_chat_template([{"role":"system","content":SYSTEM},{"role":"user","content":user}],
                                tokenize=False, add_generation_prompt=True)
    inp = tk(p, return_tensors="pt").to("cuda"); n=inp["input_ids"].shape[1]
    out = model.generate(**inp, max_new_tokens=5200, do_sample=True, eos_token_id=EOS_ID,
        pad_token_id=tk.pad_token_id, repetition_penalty=1.3, no_repeat_ngram_size=8, temperature=temp, top_p=0.9)
    return tk.decode(out[0][n:], skip_special_tokens=True).strip()

base = build_user_prompt(TOPIC, 4500)
directive = (f"\n\n**중요**: 이 대본 전체에서 환율 수치는 반드시 '{TARGET}'으로만 표기하고 "
             "다른 숫자로 임의로 바꾸지 마세요. 환율을 언급할 때는 항상 정확히 이 값을 쓰세요.")

VARIANTS = [("A baseline t0.7", base, 0.7),
            ("B inject t0.7", base + directive, 0.7),
            ("C inject t0.4", base + directive, 0.4)]
print(f"{'variant':16} {'seed':>4} {'carry':>6} {'원値종류':>8}  원값들", flush=True)
for name, user, temp in VARIANTS:
    for sd in (11, 42):
        t = gen(user, sd, temp)
        wv = won_values(t)
        print(f"{name:16} {sd:>4} {str(carry(t)):>6} {len(wv):>8}  {sorted(wv)}", flush=True)
