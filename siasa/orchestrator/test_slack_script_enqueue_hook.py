"""pre_llm_call 훅 테스트 — 결정론 enqueue 로직(슬랙 대본 생성요청 → 제작 큐).

process_payload는 순수함수: payload(dict) + add_topic(stub) → stdout 문자열.
등록은 side-effect(add_topic 호출), 답변은 {"context":...}로 유도. 비매칭/2nd턴 → "" no-op.
"""
import json

import pytest

from slack_script_enqueue_hook import process_payload


def _payload(user_message, is_first_turn=True, **extra):
    base = {"is_first_turn": is_first_turn, "user_message": user_message}
    base.update(extra)
    return {"hook_event_name": "pre_llm_call", "extra": base}


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, topic, angle="", type="C"):
        self.calls.append({"topic": topic, "angle": angle, "type": type})
        return {"id": len(self.calls), "topic": topic, "status": "pending"}


def test_second_turn_is_noop():
    rec = _Recorder()
    out = process_payload(_payload("전세사기 대본 써줘", is_first_turn=False), rec)
    assert out == "" and rec.calls == []


def test_non_generation_message_is_noop():
    rec = _Recorder()
    out = process_payload(_payload("오늘 환율 어때?"), rec)
    assert out == "" and rec.calls == []


def test_consult_with_대본_is_noop():
    # "대본"이 있어도 상담성(어때/방향/추천)은 등록하지 않고 디렉터 chat에 맡긴다
    rec = _Recorder()
    out = process_payload(_payload("전세사기 대본 방향 어때?"), rec)
    assert out == "" and rec.calls == []


def test_generation_strips_sender_prefix_and_enqueues():
    rec = _Recorder()
    out = process_payload(_payload("[gdash86] 전세사기 대챈 대본 써줘"), rec)
    assert len(rec.calls) == 1
    assert rec.calls[0]["topic"] == "전세사기 대챈"
    assert rec.calls[0]["type"] == "C"
    parsed = json.loads(out)
    assert "context" in parsed and "1" in parsed["context"]  # id 노출


def test_generation_topic_after_verb():
    rec = _Recorder()
    out = process_payload(_payload("대본 써줘 전세사기 관련"), rec)
    assert len(rec.calls) == 1
    assert rec.calls[0]["topic"] == "전세사기 관련"
    assert json.loads(out)["context"]


def test_empty_topic_asks_user_not_enqueue():
    rec = _Recorder()
    out = process_payload(_payload("대본 써줘"), rec)
    assert rec.calls == []  # 주제 없음 → 등록 안 함
    parsed = json.loads(out)
    assert "context" in parsed and ("주제" in parsed["context"])


def test_malformed_payload_is_noop():
    rec = _Recorder()
    assert process_payload({}, rec) == "" and rec.calls == []
    assert process_payload({"extra": {}}, rec) == "" and rec.calls == []


def test_missing_user_message_is_noop():
    rec = _Recorder()
    out = process_payload(_payload(None), rec)
    assert out == "" and rec.calls == []


def test_enqueue_failure_is_noop_not_crash():
    # add_topic가 던져도 훅은 디렉터를 막지 않는다(빈 출력)
    def boom(topic, angle="", type="C"):
        raise RuntimeError("queue down")

    out = process_payload(_payload("전세사기 대책 대본 작성해줘"), boom)
    assert out == ""


def test_제작_verb_also_triggers():
    rec = _Recorder()
    out = process_payload(_payload("국민연금 개혁 대본 제작해줘"), rec)
    assert len(rec.calls) == 1 and rec.calls[0]["topic"] == "국민연금 개혁"
    assert json.loads(out)["context"]
