import json, urllib.request, re, sys

model = sys.argv[1] if len(sys.argv) > 1 else "gemma4:12b"
think = (sys.argv[2].lower() == "think") if len(sys.argv) > 2 else False
soul = open("/opt/data/profiles/writer/SOUL.md", encoding="utf-8").read()
agent = open("/opt/data/profiles/writer/AGENT.md", encoding="utf-8").read()
system = soul + "\n\n" + agent
topic = (
    "주제: 원달러 환율이 천사백오십원을 넘었습니다. 이 주제로 시사베테랑 대본을 작성해 주세요.\n\n"
    "[필수 분량 — 섹션별 글자수 기준을 반드시 충족]\n"
    "가이드(지식)에 명시된 선택한 타입의 섹션별 글자수 기준을 각 섹션마다 반드시 채운다. 예를 들어 타입 B라면:\n"
    "- 도입(데이터 하나로 시작 + 후킹): 3~5문장\n"
    "- 데이터 제시: 500~800자\n"
    "- 추세 추적: 700~1,200자\n"
    "- 과거 패턴 비교: 700~1,200자\n"
    "- 경제/투자 관점 전망 + 대비책: 500~800자\n"
    "- 마무리 클로징: 100~200자\n"
    "→ 합계 본문은 반드시 4,000자 이상이 되어야 한다. 각 섹션이 기준 글자수에 미달하면 더 구체적 사례·체감 비교·쉬운 설명을 추가해 채운다.\n"
    "짧게 요약하지 말고, 각 원인과 대비책을 하나하나 길게 풀어 설명한다. 한글 숫자, 괄호 금지, 클로징 두 문장을 지킨다."
)
body = json.dumps({
    "model": model,
    "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": topic},
    ],
    "think": think,
    "stream": False,
    "options": {"num_ctx": 32768, "num_predict": 8000, "temperature": 0.7},
}).encode()
req = urllib.request.Request(
    "http://ai-source-builder-ollama-1:11434/api/chat",
    data=body, headers={"Content-Type": "application/json"},
)
try:
    r = json.load(urllib.request.urlopen(req, timeout=900))
    msg = r.get("message", {})
    out = msg.get("content", "") or ""
    thinking = msg.get("thinking", "") or ""
    open("/opt/data/g4_tuned.txt", "w", encoding="utf-8").write(out)
    print("MODEL=", model, "| think=", think)
    print("done_reason=", r.get("done_reason"))
    print("eval_count(tokens)=", r.get("eval_count"))
    print("thinking_len=", len(thinking))
    print("LEN_chars=", len(out))
    print("closing=", out.count("복잡한 세상, 제대로 읽어갑시다"))
    print("md_headers=", len(re.findall(r"(?m)^#", out)))
    print("arabic=", len(re.findall(r"[0-9]", out)))
    print("paren=", len(re.findall(r"[()]", out)))
except Exception as e:
    print("ERR", repr(e))
