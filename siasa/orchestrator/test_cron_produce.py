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


def test_transient_failure_requeues_then_errors_at_cap(tmp_path):
    # 일시 실패는 pending 재큐(다음 tick 재시도). 상한(MAX_ATTEMPTS) 초과만 error.
    # → 일시 OOM이 주제를 영구 유실시키지 않는다.
    from cron_produce import MAX_ATTEMPTS
    q, lock, ws = _paths(tmp_path)
    add_topic("주제", date="2026-06-16", path=q)
    def boom(topic, workspace):
        raise RuntimeError("생성 실패")
    for i in range(1, MAX_ATTEMPTS):           # cap 직전까지: 재큐
        with pytest.raises(RuntimeError):
            run_once(q, lock, ws, produce_runner=boom)
        rec = load_topics(q)[0]
        assert rec["status"] == "pending" and rec["attempts"] == i
    with pytest.raises(RuntimeError):           # cap 도달: error
        run_once(q, lock, ws, produce_runner=boom)
    rec = load_topics(q)[0]
    assert rec["status"] == "error" and rec["attempts"] == MAX_ATTEMPTS


def test_transient_failure_then_success_marks_done(tmp_path):
    q, lock, ws = _paths(tmp_path)
    add_topic("주제", date="2026-06-16", path=q)
    state = {"n": 0}
    def flaky(topic, workspace):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("일시 실패")
        return {"bundle_path": "/ws/bundle.json"}
    with pytest.raises(RuntimeError):
        run_once(q, lock, ws, produce_runner=flaky)   # 1차 실패 → pending
    assert load_topics(q)[0]["status"] == "pending"
    run_once(q, lock, ws, produce_runner=flaky)       # 2차 성공 → done
    assert load_topics(q)[0]["status"] == "done"


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
