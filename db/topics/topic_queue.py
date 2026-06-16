"""시사베테랑 주제 큐 — 자율 제작 작업목록(기계용). 사람/trend가 채우고 cron이 pop.

상태기계: pending → in_progress → done/error. db/decisions(사람 판정)와 분리 — 여기는 기계 work-list.
필드분절 {id, date, topic, angle, type, status}. NFC 정규화(fuse-t).

CLI: python3 topic_queue.py add --topic "..." [--angle ...] [--type C]
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from datetime import date as _date
from pathlib import Path

VALID_TYPES = {"A", "B", "C"}
VALID_STATUS = {"pending", "in_progress", "done", "error"}
DB_PATH = Path(__file__).with_name("queue.jsonl")


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def load_topics(path: str | Path = DB_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _write_all(records: list[dict], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def add_topic(topic: str, angle: str = "", type: str = "C",
              date: str | None = None, path: str | Path = DB_PATH) -> dict:
    """주제 1건 추가(status=pending, id=max+1). 경계 검증 + NFC."""
    topic_n, angle_n = _nfc(topic), _nfc(angle)
    if not topic_n:
        raise ValueError("topic(주제)은 필수입니다.")
    if type not in VALID_TYPES:
        raise ValueError(f"type은 A/B/C 중 하나여야 합니다 (받음: {type!r}).")
    records = load_topics(path)
    new_id = max((r["id"] for r in records), default=0) + 1
    rec = {
        "id": new_id,
        "date": date or _date.today().isoformat(),
        "topic": topic_n,
        "angle": angle_n,
        "type": type,
        "status": "pending",
    }
    records.append(rec)
    _write_all(records, path)
    return rec


def pop_next(path: str | Path = DB_PATH) -> dict | None:
    """가장 오래된 pending을 in_progress로 전환·영속하고 반환. 없으면 None."""
    records = load_topics(path)
    for rec in records:                       # 파일 순서 = 추가 순서(오래된 것 먼저)
        if rec["status"] == "pending":
            rec["status"] = "in_progress"
            _write_all(records, path)
            return rec
    return None


def mark(id: int, status: str, path: str | Path = DB_PATH) -> None:
    """id의 status 갱신·영속."""
    if status not in VALID_STATUS:
        raise ValueError(f"status는 {VALID_STATUS} 중 하나여야 합니다 (받음: {status!r}).")
    records = load_topics(path)
    for rec in records:
        if rec["id"] == id:
            rec["status"] = status
            _write_all(records, path)
            return
    raise KeyError(f"id={id} 없음")


def bump_attempts(id: int, path: str | Path = DB_PATH) -> int:
    """id의 ``attempts`` 카운터를 +1 하고 영속·반환. cron 재시도 상한 판정용."""
    records = load_topics(path)
    for rec in records:
        if rec["id"] == id:
            rec["attempts"] = int(rec.get("attempts", 0)) + 1
            _write_all(records, path)
            return rec["attempts"]
    raise KeyError(f"id={id} 없음")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="주제 큐 관리")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="주제 추가")
    a.add_argument("--topic", required=True)
    a.add_argument("--angle", default="")
    a.add_argument("--type", default="C")
    sub.add_parser("list", help="전체 보기")
    return ap.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    if args.cmd == "add":
        r = add_topic(args.topic, args.angle, args.type)
        print(f"추가: id={r['id']} · {r['topic']} · {r['status']}")
    else:
        for t in load_topics():
            print(f"[{t['id']}] {t['status']:<11} {t['topic']}")
