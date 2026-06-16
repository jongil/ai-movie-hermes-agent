"""확장 프로브: (1) LoRA 확장-재작성, (2) mid-cut 이어쓰기 — 길이+형식 측정."""
import os, sys, re
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

def fmt(t):
    return f"len={len(t)} arabic={len(re.findall(r'[0-9]',t))} md={len(re.findall(r'(?m)^#',t))} close={t.count(CLOSING)}"

def gen(prompt_text, max_new, seed):
    torch.manual_seed(seed)
    inp = tk(prompt_text, return_tensors="pt").to("cuda")
    n_in = inp["input_ids"].shape[1]
    out = model.generate(**inp, max_new_tokens=max_new, do_sample=True,
                        eos_token_id=EOS, pad_token_id=tk.pad_token_id, **GC)
    return tk.decode(out[0][n_in:], skip_special_tokens=True).strip()

def head_for(user):
    return tok.apply_chat_template(
        [{"role":"system","content":SYSTEM},{"role":"user","content":user}],
        tokenize=False, add_generation_prompt=True)

# 초안
draft = gen(head_for(f"주제: {TOPIC}\n\n이 주제로 시사베테랑 대본을 작성해 주세요."), 2600, 11)
print("DRAFT:", fmt(draft), flush=True)
body = strip_closing_tail(draft)

# (1) 확장-재작성
exp_user = (f"주제: {TOPIC}\n\n아래는 이 주제로 쓴 초안입니다. 같은 형식과 임한수 구어체 톤, 한글 숫자, "
            "마크다운·괄호 금지, 마지막 클로징 두 문장을 그대로 유지하되 본문을 사천자에서 육천자로 "
            "더 깊고 길게 다시 작성하세요. 각 부분에 구체적 사례와 수치, 일상 비유를 더하고 절대 요약하지 마세요.\n\n"
            f"[초안]\n{draft}")
exp = gen(head_for(exp_user), 5000, 21)
print("(1) 확장재작성:", fmt(exp), flush=True)
open(f"{BASE}/expand_rewrite.txt","w",encoding="utf-8").write(ensure_closing(exp))

# (2) mid-cut 이어쓰기: 본문 60% 지점에서 잘라 이어쓰기
cut = body[: int(len(body)*0.6)]
cont = gen(head_for(f"주제: {TOPIC}\n\n이 주제로 시사베테랑 대본을 작성해 주세요.") + cut, 2500, 31)
merged = (cut + strip_closing_tail(cont)).strip()
print("(2) mid-cut이어쓰기:", fmt(merged), f"(cut={len(cut)} → merged_body={len(merged)})", flush=True)
