"""시사베테랑 의사결정 DB — 주제별 결정(주제·타입·이유·결과)을 append 기록.

DB-first(마스터플랜): AI용 데이터는 필드분절(혼합 비고 금지). 콘텐츠 의사결정의 감사추적이자
cron 회고(시스템 자가진화)의 입력. 콘텐츠(주제) 결정용 — 프로세스 결정 아님.

append 로그(rebuild 아님): 결정 1건 = 1줄. 결과(result)는 결정 시점엔 비고 후속 기입.

실행: python3 append_decision.py --topic "..." --reason "..." [--type C] [--result ...] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from datetime import date as _date
from pathlib import Path

VALID_TYPES = {"A", "B", "C"}
DB_PATH = Path(__file__).with_name("decisions.jsonl")


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def make_decision_record(date: str, topic: str, type: str, reason: str,
                         result: str = "") -> dict[str, str]:
    """검증 + NFC 정규화한 결정 레코드. 경계 검증(필수 필드·타입)."""
    topic_n, reason_n, result_n = _nfc(topic), _nfc(reason), _nfc(result)
    if not topic_n:
        raise ValueError("topic(주제)은 필수입니다.")
    if not reason_n:
        raise ValueError("reason(이유)은 필수입니다.")
    if type not in VALID_TYPES:
        raise ValueError(f"type은 A/B/C 중 하나여야 합니다 (받음: {type!r}).")
    return {"date": date, "topic": topic_n, "type": type, "reason": reason_n, "result": result_n}


def append_decision(record: dict[str, str], path: str | Path = DB_PATH) -> None:
    """결정 레코드 1줄 append(부모 디렉터리 자동 생성, NFC·UTF-8)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_decisions(path: str | Path = DB_PATH) -> list[dict[str, str]]:
    """전체 결정 로드(회고용). 파일 없으면 빈 리스트."""
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="의사결정 DB에 결정 1건 기록")
    ap.add_argument("--topic", required=True, help="주제")
    ap.add_argument("--reason", required=True, help="이유")
    ap.add_argument("--type", default="C", help="A/B/C (기본 C)")
    ap.add_argument("--result", default="", help="결과(후속 기입 가능)")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (기본 오늘)")
    ap.add_argument("--db", default=str(DB_PATH), help="DB 경로")
    return ap.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    d = args.date or _date.today().isoformat()
    rec = make_decision_record(d, args.topic, args.type, args.reason, args.result)
    append_decision(rec, args.db)
    print(f"기록: {d} · {rec['topic']} · type={rec['type']} → {args.db}")
