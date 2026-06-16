"""주제 큐 테스트 — 상태기계(pending/in_progress/done/error) + 필드분절."""
import unicodedata

import pytest

from topic_queue import add_topic, load_topics, pop_next, mark, VALID_STATUS, _parse_args


def test_add_assigns_id_and_pending(tmp_path):
    p = str(tmp_path / "q.jsonl")
    r = add_topic("환율 급등", angle="장바구니 물가", date="2026-06-16", path=p)
    assert r["id"] == 1 and r["status"] == "pending" and r["type"] == "C"
    assert r["topic"] == "환율 급등" and r["angle"] == "장바구니 물가"


def test_add_increments_id(tmp_path):
    p = str(tmp_path / "q.jsonl")
    add_topic("주제1", date="2026-06-16", path=p)
    r2 = add_topic("주제2", date="2026-06-16", path=p)
    assert r2["id"] == 2


def test_add_requires_topic(tmp_path):
    with pytest.raises(ValueError):
        add_topic("   ", date="2026-06-16", path=str(tmp_path / "q.jsonl"))


def test_add_validates_type(tmp_path):
    with pytest.raises(ValueError):
        add_topic("주제", type="X", date="2026-06-16", path=str(tmp_path / "q.jsonl"))


def test_add_nfc_normalizes(tmp_path):
    p = str(tmp_path / "q.jsonl")
    r = add_topic(unicodedata.normalize("NFD", "환율"), date="2026-06-16", path=p)
    assert r["topic"] == unicodedata.normalize("NFC", "환율")


def test_pop_next_oldest_pending_to_in_progress(tmp_path):
    p = str(tmp_path / "q.jsonl")
    add_topic("주제1", date="2026-06-16", path=p)
    add_topic("주제2", date="2026-06-17", path=p)
    popped = pop_next(p)
    assert popped["topic"] == "주제1" and popped["status"] == "in_progress"
    # 영속: 다시 로드해도 in_progress
    assert next(t for t in load_topics(p) if t["id"] == 1)["status"] == "in_progress"


def test_pop_next_none_when_no_pending(tmp_path):
    p = str(tmp_path / "q.jsonl")
    add_topic("주제", date="2026-06-16", path=p)
    pop_next(p)                 # 유일 주제 → in_progress
    assert pop_next(p) is None  # 더 pending 없음


def test_pop_next_empty_file(tmp_path):
    assert pop_next(str(tmp_path / "none.jsonl")) is None


def test_mark_updates_status(tmp_path):
    p = str(tmp_path / "q.jsonl")
    add_topic("주제", date="2026-06-16", path=p)
    mark(1, "done", p)
    assert load_topics(p)[0]["status"] == "done"


def test_mark_validates_status(tmp_path):
    p = str(tmp_path / "q.jsonl")
    add_topic("주제", date="2026-06-16", path=p)
    with pytest.raises(ValueError):
        mark(1, "bogus", p)
    assert "bogus" not in VALID_STATUS


def test_mark_missing_id_raises(tmp_path):
    p = str(tmp_path / "q.jsonl")
    add_topic("주제", date="2026-06-16", path=p)
    with pytest.raises(KeyError):
        mark(999, "done", p)


def test_parse_args_add():
    ns = _parse_args(["add", "--topic", "t", "--angle", "a", "--type", "B"])
    assert ns.cmd == "add" and ns.topic == "t" and ns.angle == "a" and ns.type == "B"
