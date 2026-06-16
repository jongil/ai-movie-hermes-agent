"""의사결정 DB append/load 테스트 — 필드분절(주제·타입·이유·결과) + 경계 검증."""
import unicodedata

import pytest

from append_decision import (
    make_decision_record, append_decision, load_decisions, _parse_args,
)


def test_make_record_valid():
    r = make_decision_record("2026-06-16", "환율 급등", "C", "시의성 높음", result="발행")
    assert r == {
        "date": "2026-06-16", "topic": "환율 급등", "type": "C",
        "reason": "시의성 높음", "result": "발행",
    }


def test_make_record_default_result_empty():
    r = make_decision_record("2026-06-16", "주제", "C", "이유")
    assert r["result"] == ""        # 결과는 결정 시점엔 비고 후속 기입


def test_make_record_requires_topic():
    with pytest.raises(ValueError):
        make_decision_record("2026-06-16", "  ", "C", "이유")


def test_make_record_requires_reason():
    with pytest.raises(ValueError):
        make_decision_record("2026-06-16", "주제", "C", "")


def test_make_record_validates_type():
    with pytest.raises(ValueError):
        make_decision_record("2026-06-16", "주제", "X", "이유")


def test_make_record_nfc_normalizes():
    # fuse-t NFD 입력도 NFC로 저장(파일명·문자열 매칭 일관)
    nfd = unicodedata.normalize("NFD", "환율")
    r = make_decision_record("2026-06-16", nfd, "C", "이유")
    assert r["topic"] == unicodedata.normalize("NFC", "환율")


def test_append_and_load_roundtrip(tmp_path):
    p = tmp_path / "decisions.jsonl"
    append_decision(make_decision_record("2026-06-16", "주제1", "C", "이유1"), str(p))
    append_decision(make_decision_record("2026-06-17", "주제2", "C", "이유2", result="보류"), str(p))
    recs = load_decisions(str(p))
    assert len(recs) == 2
    assert recs[0]["topic"] == "주제1"
    assert recs[1]["result"] == "보류"


def test_append_creates_parent_dir(tmp_path):
    p = tmp_path / "sub" / "decisions.jsonl"
    append_decision(make_decision_record("2026-06-16", "주제", "C", "이유"), str(p))
    assert load_decisions(str(p))[0]["topic"] == "주제"


def test_load_missing_returns_empty(tmp_path):
    assert load_decisions(str(tmp_path / "none.jsonl")) == []


def test_parse_args_defaults():
    ns = _parse_args(["--topic", "t", "--reason", "r"])
    assert ns.topic == "t" and ns.reason == "r"
    assert ns.type == "C" and ns.result == "" and ns.date is None


def test_parse_args_overrides():
    ns = _parse_args(["--topic", "t", "--reason", "r", "--type", "A",
                      "--result", "x", "--date", "2026-06-16"])
    assert ns.type == "A" and ns.result == "x" and ns.date == "2026-06-16"
