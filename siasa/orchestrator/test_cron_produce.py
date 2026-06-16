"""cron_produce 테스트 — lock·pop·done/error 상태기계. produce_episode stub(GPU 0)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "db" / "topics"))
from topic_queue import add_topic, load_topics  # noqa: E402
from cron_produce import run_once, _acquire, _release, _parse_args, _slug  # noqa: E402


def _ok_producer(bundle="/ws/bundle.json"):
    calls = []
    def run(topic, workspace):
        calls.append((topic, workspace))
        return {"bundle_path": bundle}
    run.calls = calls
    return run


def _paths(tmp_path):
    return str(tmp_path / "q.jsonl"), str(tmp_path / ".lock"), str(tmp_path / "ws")


def test_produces_one_and_marks_done(tmp_path):
    q, lock, ws = _paths(tmp_path)
    add_topic("환율 급등", date="2026-06-16", path=q)
    prod = _ok_producer()
    msg = run_once(q, lock, ws, produce_runner=prod)
    assert prod.calls and prod.calls[0][0] == "환율 급등"
    assert load_topics(q)[0]["status"] == "done"
    assert "제작 완료" in msg


def test_skip_when_locked(tmp_path):
    q, lock, ws = _paths(tmp_path)
    add_topic("주제", date="2026-06-16", path=q)
    _acquire(lock)                          # 다른 실행이 락 보유 중
    prod = _ok_producer()
    assert run_once(q, lock, ws, produce_runner=prod) is None
    assert not prod.calls                   # 생성 미진입
    assert load_topics(q)[0]["status"] == "pending"   # pop 안 함
    _release(lock)


def test_silent_when_empty_queue(tmp_path):
    q, lock, ws = _paths(tmp_path)
    prod = _ok_producer()
    assert run_once(q, lock, ws, produce_runner=prod) is None
    assert not prod.calls


def test_failure_marks_error_and_raises(tmp_path):
    q, lock, ws = _paths(tmp_path)
    add_topic("주제", date="2026-06-16", path=q)
    def boom(topic, workspace):
        raise RuntimeError("생성 실패")
    with pytest.raises(RuntimeError):
        run_once(q, lock, ws, produce_runner=boom)
    assert load_topics(q)[0]["status"] == "error"


def test_lock_released_after_run(tmp_path):
    q, lock, ws = _paths(tmp_path)
    add_topic("주제", date="2026-06-16", path=q)
    run_once(q, lock, ws, produce_runner=_ok_producer())
    assert not Path(lock).exists()          # 락 해제됨 → 다음 tick 가능


def test_only_one_per_run(tmp_path):
    q, lock, ws = _paths(tmp_path)
    add_topic("주제1", date="2026-06-16", path=q)
    add_topic("주제2", date="2026-06-17", path=q)
    prod = _ok_producer()
    run_once(q, lock, ws, produce_runner=prod)
    assert len(prod.calls) == 1             # tick당 1편
    statuses = {t["id"]: t["status"] for t in load_topics(q)}
    assert statuses[1] == "done" and statuses[2] == "pending"


def test_release_idempotent(tmp_path):
    lock = str(tmp_path / ".lock")
    _release(lock)                          # 없는 락 해제 → 에러 없음
    assert _acquire(lock) and not _acquire(lock)   # 획득 후 재획득 실패(점유)
    _release(lock)


def test_slug_and_parse_args():
    assert _slug("환율 급등!") == "환율_급등_"
    ns = _parse_args(["--queue", "/q", "--lock", "/l"])
    assert ns.queue == "/q" and ns.lock == "/l"
