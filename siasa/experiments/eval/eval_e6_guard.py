"""e6 어댑터 평가: 안정 gen config + 가드(ensure_closing) → 발행가능 도달 여부."""
import os, sys
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
sys.path.insert(0, "/home/gdash86/project/ai-movie-hermes-agent")
from unsloth import FastModel
import torch
from script_guard import ensure_closing, needs_retry, is_publishable, detect_degenerate, CLOSING

BASE = "/home/gdash86/project/ai-movie-hermes-agent"
LORA = os.environ.get("LORA", f"{BASE}/siasa_lora_e6")
EOS = 106
SYSTEM = ("당신은 시사 베테랑 채널의 임한수 작가입니다. 주어진 주제로 5070 시니어 대상 시사·경제 "
          "유튜브 내레이션 대본을 작성합니다. 팩트 기반 분석, 후킹 도입, 쉬운 말 변환, 한글 숫자 표기, "
          "마지막 채널 멘트를 지킵니다.")
TOPICS = ["원달러 환율이 천사백오십원을 넘었습니다", "국민연금 개혁안이 발표되었습니다"]

print("LORA=", LORA, flush=True)
model, tok = FastModel.from_pretrained(LORA, max_seq_length=8192, load_in_4bit=True)
FastModel.for_inference(model)
tk = getattr(tok, "tokenizer", tok)

def body_len(text):
    return len(text.split(CLOSING)[0]) if CLOSING in text else len(text)

GC = dict(repetition_penalty=1.3, no_repeat_ngram_size=8, temperature=0.7, top_p=0.9)
SEEDS = [11, 42, 77]
MAXNEW = 4500

print(f"{'topic':10} {'seed':>4} {'tok':>5} {'stop':>5} {'body':>5} {'rawC':>4} {'finalC':>6} {'pub':>4}")
pub_ct = 0; total = 0
for ti, topic in enumerate(TOPICS):
    msgs = [{"role":"system","content":SYSTEM},
            {"role":"user","content":f"주제: {topic}\n\n이 주제로 시사베테랑 대본을 작성해 주세요."}]
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = tk(prompt, return_tensors="pt").to("cuda")
    n_in = inp["input_ids"].shape[1]
    for sd in SEEDS:
        torch.manual_seed(sd)
        out = model.generate(**inp, max_new_tokens=MAXNEW, do_sample=True,
                             eos_token_id=EOS, pad_token_id=tk.pad_token_id, **GC)
        g = out[0][n_in:]; n = g.shape[0]
        raw = tk.decode(g, skip_special_tokens=True).strip()
        final = ensure_closing(raw)
        pub = is_publishable(final)
        pub_ct += pub; total += 1
        print(f"T{ti:<9} {sd:>4} {n:>5} {str(n<MAXNEW):>5} {body_len(raw):>5} {raw.count(CLOSING):>4} {final.count(CLOSING):>6} {str(pub):>4}", flush=True)
        if ti==0 and sd==11:
            open(f"{BASE}/e6_sample.txt","w",encoding="utf-8").write(final)
print(f"\n=== 가드 적용 후 발행가능: {pub_ct}/{total} ===")
print("(body=클로징 제외 본문길이, rawC=모델클로징, finalC=가드후클로징, pub=is_publishable)")
