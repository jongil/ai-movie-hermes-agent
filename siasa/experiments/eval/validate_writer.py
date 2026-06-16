"""작가 파이프라인 검증: 아웃라인+best-of-N+가드, 다중 토픽 발행가능률."""
import os, sys, re
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
sys.path.insert(0, "/home/gdash86/project/ai-movie-hermes-agent")
from unsloth import FastModel
import torch
from siasa_writer import SYSTEM, build_user_prompt, pick_best, GEN_CONFIG, EOS_ID
from script_guard import is_publishable, CLOSING

BASE = "/home/gdash86/project/ai-movie-hermes-agent"
LORA = f"{BASE}/siasa_lora_e6"
TOPICS = ["원달러 환율이 천사백오십원을 넘었습니다",
          "국민연금 개혁안이 발표되었습니다",
          "서울 아파트값이 다시 오르고 있습니다"]
SEEDS = [11, 42, 77]

model, tok = FastModel.from_pretrained(LORA, max_seq_length=8192, load_in_4bit=True)
FastModel.for_inference(model)
tk = getattr(tok, "tokenizer", tok)

def gen_one(user, seed):
    torch.manual_seed(seed)
    p = tok.apply_chat_template([{"role":"system","content":SYSTEM},{"role":"user","content":user}],
                                tokenize=False, add_generation_prompt=True)
    inp = tk(p, return_tensors="pt").to("cuda"); n=inp["input_ids"].shape[1]
    out = model.generate(**inp, max_new_tokens=5200, do_sample=True, eos_token_id=EOS_ID,
                        pad_token_id=tk.pad_token_id, **GEN_CONFIG)
    return tk.decode(out[0][n:], skip_special_tokens=True).strip()

pub_ct = 0
print(f"{'topic':6} {'cand_lens':22} {'final':>6} {'pub':>5}")
for ti, topic in enumerate(TOPICS):
    user = build_user_prompt(topic, 4500)
    cands = [gen_one(user, sd) for sd in SEEDS]
    final, ok = pick_best(cands)
    pub_ct += is_publishable(final)
    print(f"T{ti:<5} {str([len(c) for c in cands]):22} {len(final):>6} {str(ok):>5}", flush=True)
    open(f"{BASE}/writer_T{ti}.txt","w",encoding="utf-8").write(final)
print(f"\n=== 발행가능: {pub_ct}/{len(TOPICS)} 토픽 (best-of-{len(SEEDS)}) ===")
