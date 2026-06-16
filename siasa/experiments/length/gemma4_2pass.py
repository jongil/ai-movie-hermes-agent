import json, urllib.request, re

URL = "http://ai-source-builder-ollama-1:11434/api/chat"
soul = open("/opt/data/profiles/writer/SOUL.md", encoding="utf-8").read()
agent = open("/opt/data/profiles/writer/AGENT.md", encoding="utf-8").read()
system = soul + "\n\n" + agent


def call(messages, num_predict=8000):
    body = json.dumps({
        "model": "gemma4:12b", "messages": messages, "think": False, "stream": False,
        "options": {"num_ctx": 32768, "num_predict": num_predict, "temperature": 0.7},
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=900))
    return r["message"].get("content", "") or ""


def stats(label, t):
    print(f"{label}: len={len(t)} closing={t.count('복잡한 세상, 제대로 읽어갑시다')} "
          f"md={len(re.findall(r'(?m)^#', t))} arabic={len(re.findall(r'[0-9]', t))} paren={len(re.findall(r'[()]', t))}")


# Pass 1 — draft
topic = "주제: 원달러 환율이 천사백오십원을 넘었습니다. 이 주제로 시사베테랑 대본을 작성해 주세요."
draft = call([{"role": "system", "content": system}, {"role": "user", "content": topic}])
stats("PASS1", draft)

# Pass 2 — expand to length, keep format
expand = (
    "아래는 너가 쓴 시사베테랑 대본 초안이다. 형식([타입 선택]/[대본]/[검수 결과]), 임한수 구어체 톤, 한글 숫자, "
    "괄호 금지, 클로징 두 문장은 그대로 유지하되, **본문이 4,000자 이상 6,000자 이하가 되도록 확장**하라.\n"
    "확장 방법: 각 원인과 대비책마다 구체적 사례, 체감 가능한 비교(1인당·몇 명 중 몇 명·일상 비유), 쉬운 설명을 더 붙인다. "
    "새 섹션을 만들지 말고 기존 흐름을 더 깊고 길게 풀어라. 요약하지 마라.\n\n"
    "[초안]\n" + draft
)
cur = draft
for i in range(2, 6):
    ex = (
        "아래는 시사베테랑 대본 초안이다. 형식([타입 선택]/[대본]/[검수 결과]), 임한수 구어체 톤, 한글 숫자, "
        "괄호 금지, 클로징 두 문장은 그대로 유지하되, **본문이 4,000자 이상 6,000자 이하가 되도록 더 확장**하라.\n"
        "각 원인과 대비책마다 구체적 사례, 체감 비교(1인당·일상 비유), 쉬운 설명을 더 붙인다. 새 섹션 만들지 말고 기존 흐름을 더 깊게 풀어라. 요약 금지.\n\n"
        "[초안]\n" + cur
    )
    cur = call([{"role": "system", "content": system}, {"role": "user", "content": ex}])
    stats(f"PASS{i}", cur)
    if len(cur) >= 4000:
        break
open("/opt/data/g4_2pass.txt", "w", encoding="utf-8").write(cur)
print("FINAL_len=", len(cur))
