"""cron 자율 제작 래퍼 — 결정론(LLM 자율 없음). 주제 큐 pop → produce_episode → 상태 갱신.

cron `--no-agent --script`로 스케줄 실행. tick당 1편(lock으로 overrun 차단). 종료보장=함수 반환.
성공→done+번들 stdout / 실패→error+예외(stderr). 빈 큐/락점유→silent(None).

상세·배포: SKILL.md.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve()
HERMES_HOME = os.environ.get("HERMES_DIR", "/opt/data")
sys.path.insert(0, str(_HERE.parents[2] / "db" / "topics"))
from topic_queue import pop_next, mark, bump_attempts  # noqa: E402

# 일시 실패(로드 OOM·BACKEND_UNAVAILABLE 등) 재시도 상한. 초과 시에만 error.
# 문자열로 일시/영구를 분류하지 않는다 — 콘텐츠 실패는 드물어 헛재시도가 저렴하고,
# 오분류로 인한 주제 영구 유실(stranding)을 피한다.
MAX_ATTEMPTS = 3

QUEUE_PATH = f"{HERMES_HOME}/db/topics/queue.jsonl"
LOCK_PATH = f"{HERMES_HOME}/workspace/.produce.lock"
WORKSPACE_BASE = os.environ.get("SIASA_OUT_DIR") or f"{HERMES_HOME}/workspace/episodes"


def _acquire(lock_path: str) -> bool:
    """원자적 락 획득(O_EXCL). 이미 있으면 False(다른 실행 진행 중)."""
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _release(lock_path: str) -> None:
    try:
        os.remove(lock_path)
    except FileNotFoundError:
        pass


def _slug(topic: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in topic)[:40] or "episode"


def _default_produce(topic: str, workspace: str) -> dict:
    from produce_episode import produce_episode
    return produce_episode(topic, workspace)


def run_once(
    queue_path: str = QUEUE_PATH,
    lock_path: str = LOCK_PATH,
    workspace_base: str = WORKSPACE_BASE,
    produce_runner: Callable[[str, str], dict] | None = None,
) -> str | None:
    """1 tick = 최대 1편. 락 점유/빈 큐면 None(silent). 성공 메시지 반환, 실패 예외."""
    produce_runner = produce_runner or _default_produce
    if not _acquire(lock_path):
        return None                                   # 진행 중 → skip(중복 차단)
    try:
        topic = pop_next(queue_path)                  # pending→in_progress
        if topic is None:
            return None                               # 빈 큐 → silent
        ws = str(Path(workspace_base) / _slug(topic["topic"]))
        try:
            rep = produce_runner(topic["topic"], ws)
        except Exception:
            attempts = bump_attempts(topic["id"], queue_path)
            # 상한 전이면 pending 재큐(다음 tick 재시도), 초과면 error. 실패는 그대로 전파(stderr 가시성).
            mark(topic["id"], "error" if attempts >= MAX_ATTEMPTS else "pending", queue_path)
            raise
        mark(topic["id"], "done", queue_path)
        return f"제작 완료: id={topic['id']} · {topic['topic']} → {rep.get('bundle_path')}"
    finally:
        _release(lock_path)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="cron 자율 제작 1 tick")
    ap.add_argument("--queue", default=QUEUE_PATH)
    ap.add_argument("--lock", default=LOCK_PATH)
    ap.add_argument("--workspace-base", default=WORKSPACE_BASE)
    return ap.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    msg = run_once(args.queue, args.lock, args.workspace_base)
    if msg:
        print(msg)                                    # --no-agent: stdout 전달. 빈 출력=silent.
    sys.exit(0)
