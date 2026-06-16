"""아웃라인 스캐폴딩 프로브: 구체 소제목 목록을 주면 단일패스가 길어지는가."""
import os, sys, re
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
sys.path.insert(0, "/home/gdash86/project/ai-movie-hermes-agent")
from unsloth import FastModel
import torch
from script_guard import ensure_closing, CLOSING

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
def fmt(t): return f"len={len(t)} arabic={len(re.findall(r'[0-9]',t))} md={len(re.findall(r'(?m)^#',t))} close={t.count(CLOSING)}"
def gen(user, max_new, seed):
    torch.manual_seed(seed)
    p = tok.apply_chat_template([{"role":"system","content":SYSTEM},{"role":"user","content":user}],
                                tokenize=False, add_generation_prompt=True)
    inp = tk(p, return_tensors="pt").to("cuda"); n=inp["input_ids"].shape[1]
    out = model.generate(**inp, max_new_tokens=max_new, do_sample=True, eos_token_id=EOS,
                        pad_token_id=tk.pad_token_id, **GC)
    return tk.decode(out[0][n:], skip_special_tokens=True).strip()

outline_user = (
    f"주제: {TOPIC}\n\n"
    "이 주제로 시사베테랑 대본을 작성하되, 아래 흐름을 모두 충분히 길고 깊게 풀어 전체 본문이 "
    "사천오백자 이상이 되게 작성해 주세요. 각 단락마다 구체적 수치(한글), 사례, 일상 비유를 넣고 절대 요약하지 마세요.\n"
    "1) 충격적 사실로 시작하는 후킹 도입\n"
    "2) 왜 이런 일이 벌어졌는지 큰 그림\n"
    "3) 첫 번째 원인 자세히\n"
    "4) 두 번째 원인 자세히\n"
    "5) 세 번째 원인 자세히\n"
    "6) 우리 생활 물가에 미치는 영향\n"
    "7) 기업과 일자리에 미치는 영향\n"
    "8) 금융시장과 자산에 미치는 영향\n"
    "9) 정부의 대응과 그 한계\n"
    "10) 앞으로의 전망\n"
    "11) 시청자가 준비할 세 가지 대비책\n"
    "12) 마무리 인사와 클로징 두 문장\n"
)
for sd in (11, 42):
    t = gen(outline_user, 6000, sd)
    print(f"아웃라인 seed{sd}:", fmt(t), flush=True)
    if sd == 11:
        open(f"{BASE}/outline_sample.txt","w",encoding="utf-8").write(ensure_closing(t))
