import json, urllib.request, re, sys

model = sys.argv[1] if len(sys.argv) > 1 else "gemma4:12b"
soul = open("/opt/data/profiles/writer/SOUL.md", encoding="utf-8").read()
agent = open("/opt/data/profiles/writer/AGENT.md", encoding="utf-8").read()
system = soul + "\n\n" + agent
topic = "주제: 원달러 환율이 천사백오십원을 넘었습니다. 이 주제로 시사베테랑 대본을 작성해 주세요."
body = json.dumps({
    "model": model,
    "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": topic},
    ],
    "max_tokens": 6000,
    "temperature": 0.7,
}).encode()
req = urllib.request.Request(
    "http://ai-source-builder-ollama-1:11434/v1/chat/completions",
    data=body, headers={"Content-Type": "application/json"},
)
try:
    r = json.load(urllib.request.urlopen(req, timeout=600))
    ch = r["choices"][0]
    msg = ch["message"]
    out = msg.get("content", "") or ""
    print("MODEL=", model)
    print("finish_reason=", ch.get("finish_reason"))
    print("usage=", r.get("usage"))
    print("msg_keys=", list(msg.keys()))
    print("reasoning_len=", len(msg.get("reasoning") or ""))
    print("reasoning_head=", (msg.get("reasoning") or "")[:300])
    print("LEN_chars=", len(out))
    print("closing=", out.count("복잡한 세상, 제대로 읽어갑시다"))
    print("md_headers=", len(re.findall(r"(?m)^#", out)))
    print("arabic=", len(re.findall(r"[0-9]", out)))
    print("paren=", len(re.findall(r"[()]", out)))
    open("/opt/data/g4_daebon.txt", "w", encoding="utf-8").write(out)
    print("=== FULL DAEBON (content) ===")
    print(out)
except Exception as e:
    print("ERR", repr(e))
