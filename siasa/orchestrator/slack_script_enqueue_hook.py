#!/usr/bin/env python3
"""pre_llm_call shell hook — 슬랙 대본 생성요청을 결정론적으로 제작 큐에 등록.

hermes `pre_llm_call` 페이로드(stdin JSON)를 받아, `is_first_turn` + intent regex로
"대본 생성요청"을 판정하면 `topic_queue`에 등록(side-effect)하고 `{"context":...}`로
디렉터 답변을 유도한다(본문 직접작성 금지). 비매칭/2nd턴/상담성 → 빈 출력(no-op).

등록은 LLM 판단 **밖**의 결정론 side-effect다 — 프롬프트-only 라우팅 실패
([[plans/20260616-2224-slack-script-route-to-v1writer]] live-NEGATIVE)를 회피한다.
배선: config.yaml `hooks.pre_llm_call` → 이 스크립트, headless consent = `hooks_auto_accept: true`.
페이로드 필드: `extra.{user_message, is_first_turn}` (실측 확인). `user_message`엔 `[sender]` 접두가 붙는다.
"""
from __future__ import annotations

import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# siasa/orchestrator → repo/db/topics (cron_produce.py와 동일 import 패턴)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "db", "topics"))

_SENDER = re.compile(r"^\s*\[[^\]]*\]\s*")
_CONSULT = re.compile(r"(어때|어떨까|어떻게\s*생각|괜찮|추천|의견|방향|조언|좋을까|좋을지)")
_HAS_SCRIPT = re.compile(r"대본")
_HAS_GEN_VERB = re.compile(r"(써|쓰|작성|제작|만들)")
# 주제 추출용 생성-토큰 제거(긴 복합 먼저). 단독 음절(써/쓰/줘)은 제거하지 않는다
# — 주제어(예: "쓰레기 정책")의 오삭제 방지.
_GEN_TOKENS = re.compile(
    r"(대본|써\s*줘|써\s*주세요|작성해\s*줘|작성해주세요|작성|제작해\s*줘|제작해주세요|제작|"
    r"만들어\s*줘|만들어주세요|만들어|해\s*줘|부탁합니다|부탁해줘|부탁해|부탁드려요|좀)"
)


def _strip_sender(msg: str | None) -> str:
    return _SENDER.sub("", msg or "").strip()


def _is_generation(msg: str) -> bool:
    if _CONSULT.search(msg):
        return False  # 상담성은 디렉터 chat에 맡김
    return bool(_HAS_SCRIPT.search(msg) and _HAS_GEN_VERB.search(msg))


def _extract_topic(msg: str) -> str:
    stripped = _GEN_TOKENS.sub(" ", msg)
    return re.sub(r"\s+", " ", stripped).strip(" ,.—-")


def process_payload(payload, add_topic) -> str:
    """순수함수: 페이로드 + add_topic(콜러블) → stdout 문자열.

    add_topic(topic, angle="", type="C") -> dict(id 포함). 테스트는 stub 주입.
    """
    extra = payload.get("extra") if isinstance(payload, dict) else None
    if not isinstance(extra, dict):
        extra = payload if isinstance(payload, dict) else {}
    if not extra.get("is_first_turn"):
        return ""
    msg = _strip_sender(extra.get("user_message"))
    if not msg or not _is_generation(msg):
        return ""
    topic = _extract_topic(msg)
    if not topic:
        return json.dumps(
            {"context": ("사용자가 대본 생성을 요청했으나 주제가 비었다. "
                         "어떤 주제로 만들지 한 줄로 되물어라(직접 대본을 쓰지 말 것).")},
            ensure_ascii=False,
        )
    try:
        rec = add_topic(topic, angle="", type="C")
    except Exception:
        return ""  # 등록 실패해도 디렉터 턴을 막지 않는다(no-op)
    return json.dumps(
        {"context": (
            f"[시스템] 사용자의 대본 생성요청을 제작 큐에 등록함(id={rec.get('id')}, 주제: {topic}). "
            f"cron 결정론 파이프가 백그라운드로 풀번들(분량 스캐폴딩+게이트)을 제작한다. "
            f"사용자에게: 큐 등록 완료(id={rec.get('id')})와 산출물이 workspace/episodes/에 "
            f"저장됨을 간단히 알려라. 본문 대본을 직접 쓰지 말 것.")},
        ensure_ascii=False,
    )


def _real_add_topic(topic, angle="", type="C"):
    import topic_queue  # noqa: E402 (런타임 path 주입 후 import)
    return topic_queue.add_topic(topic, angle=angle, type=type)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        print("")
        return 0
    try:
        out = process_payload(payload, _real_add_topic)
    except Exception:
        out = ""
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
