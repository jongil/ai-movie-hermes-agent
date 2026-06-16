"""시사베테랑 대본 코퍼스 → QLoRA 학습용 JSONL (chat format).

설계:
- 학습쌍 = system(짧은 페르소나) + user(주제) → assistant(원본 대본 narration).
  · 타깃은 원본 대본.txt 그대로 (= seam/split_scenes 입력 포맷). 래퍼([타입선택]/[검수결과]) 없음.
  · 형식·분량·톤·클로징·한글숫자를 가중치에 학습 → 추론 시 거대 지침 없이 단일패스.
- 주제(입력)는 각 대본 앞부분에서 로컬 gemma4로 한 줄 추출 → 추론 입력과 동일 형태.
- 필터: 클로징 멘트 존재 + 길이 3,000~7,000자 (손상/템플릿 제외).

실행(서버, ollama 네트워크): ~/unsloth-venv/bin/python prepare_training_data.py
"""
import os, json, glob, urllib.request

CORPUS_DIR = os.environ.get("CORPUS_DIR", "/opt/data/corpus")   # YYYY-MM-DD.txt 들
OUT = os.environ.get("OUT", "/opt/data/train.jsonl")
OLLAMA = os.environ.get("OLLAMA_URL", "http://ai-source-builder-ollama-1:11434/api/chat")
CLOSING = "복잡한 세상, 제대로 읽어갑시다"
MIN_LEN, MAX_LEN = 3000, 7000

SYSTEM = (
    "당신은 시사 베테랑 채널의 임한수 작가입니다. "
    "주어진 주제로 5070 시니어 대상 시사·경제 유튜브 내레이션 대본을 작성합니다. "
    "팩트 기반 분석, 후킹 도입, 쉬운 말 변환, 한글 숫자 표기, 마지막 채널 멘트를 지킵니다."
)


def gen_topic(daebon: str) -> str:
    """대본 앞부분으로 한 줄 주제(명사구) 추출 — 추론 시 받을 '주제'와 동일 형태."""
    head = daebon[:700]
    prompt = (
        "다음 시사베테랑 대본이 다루는 핵심 주제를 한국어 한 줄(20자 이내, 명사구)로만 답하라. "
        "설명·따옴표·기호 없이 주제만.\n\n" + head
    )
    body = json.dumps({
        "model": "gemma4:12b",
        "messages": [{"role": "user", "content": prompt}],
        "think": False, "stream": False,
        "options": {"num_ctx": 4096, "num_predict": 40, "temperature": 0.3},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    return r["message"]["content"].strip().splitlines()[0].strip().strip('"').strip()[:40]


def main():
    files = sorted(glob.glob(f"{CORPUS_DIR}/*.txt"))
    examples, skipped = [], []
    for f in files:
        text = open(f, encoding="utf-8").read().strip()
        n = len(text)
        if CLOSING not in text or not (MIN_LEN <= n <= MAX_LEN):
            skipped.append((os.path.basename(f), n, CLOSING in text))
            continue
        topic = gen_topic(text)
        examples.append({"messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"주제: {topic}\n\n이 주제로 시사베테랑 대본을 작성해 주세요."},
            {"role": "assistant", "content": text},
        ]})
        print(f"OK  {os.path.basename(f):16} | {n}자 | 주제: {topic}")

    with open(OUT, "w", encoding="utf-8") as w:
        for ex in examples:
            w.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\n=== 정제 완료: {len(examples)}개 학습쌍 → {OUT} (제외 {len(skipped)}개) ===")
    for name, n, has_close in skipped:
        print(f"  SKIP {name} (len={n}, closing={has_close})")


if __name__ == "__main__":
    main()
