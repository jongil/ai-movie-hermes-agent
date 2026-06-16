"""시사베테랑 코퍼스 인덱스 빌더 — 현행 발행본을 토픽 검색용 카탈로그로.

소비자 쿼리(DB-first): "이 주제와 유사한 과거편 1~2개". 그에 필요한 최소 스키마만 담는다:
  {date, title, type, path}
- title: day 폴더 docs/*.docx **파일명**(37/39 보유, 노이즈 접미 제거). 없으면 대본 첫 문장 폴백.
- type: 사용자 확정 — 2026-05 이후 전부 C(맥락 해설형). 04월(현행 시작분)은 미확인(거짓 라벨 금지).
- 스타일 피처(분량·문장길이 등)는 의도적으로 제외 — baseline_profile.json과 중복, 토픽 검색에 무용.

실행: python3 build_corpus_index.py [코퍼스_glob]   → db/corpus/index.jsonl
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

# 현행 컨벤션 선별용(구조 게이트 통과편 = 현행 39편)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "siasa" / "writer"))
from script_guard import is_publishable  # noqa: E402

DEFAULT_GLOB = "/Users/gdash/docs/경제베테랑-youtube/2026-*/대본.txt"
# 현행 컨벤션 시작(2026-04-13) 이후 전부 C(맥락 해설형). 5월+ 사용자 확정, 04월 16편은
# 도입/본문 구조 대조로 확정(2026-06-16). 이전(컨벤션 미만)은 unconfirmed.
TYPE_CUTOFF = "2026-04-13"
_NOISE_SUFFIXES = {"분석", "가이드라인", "지침"}
_SENT_END = re.compile(r"[.!?。]")


def clean_title(raw: str) -> str:
    """제목 노이즈 접미(분석/가이드라인/지침) 제거 + 공백 정리.

    macOS 파일명은 NFD(자모 분해) 한글이라 NFC 리터럴과 `in` 매칭이 실패한다 → NFC 정규화 선행.
    """
    tokens = unicodedata.normalize("NFC", raw).strip().split()
    while tokens and tokens[-1] in _NOISE_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def type_for_date(date: str) -> str:
    """2026-05-01 이후 = C(확정), 그 전(04월 현행 시작분) = unconfirmed."""
    return "C" if date >= TYPE_CUTOFF else "unconfirmed"


def make_record(date: str, title: str, path: str) -> dict[str, str]:
    return {"date": date, "title": title, "type": type_for_date(date), "path": path}


def _first_sentence(text: str) -> str:
    """docx 제목 부재 시 폴백 — 대본 첫 문장(NFC 정규화)."""
    m = _SENT_END.search(text)
    return unicodedata.normalize("NFC", (text[: m.start()] if m else text[:60]).strip())


def extract_title(day_dir: str, script_text: str) -> str:
    """day 폴더 docs/*.docx 파일명(정리) 우선, 없으면 첫 문장 폴백."""
    docx = sorted(glob.glob(os.path.join(day_dir, "docs", "*.docx")))
    if docx:
        return clean_title(os.path.splitext(os.path.basename(docx[0]))[0])
    return _first_sentence(script_text)


def build_index(corpus_glob: str = DEFAULT_GLOB) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for path in sorted(glob.glob(corpus_glob)):
        text = Path(path).read_text(encoding="utf-8")
        if not is_publishable(text):             # 현행 컨벤션만(구포맷 제외)
            continue
        day_dir = os.path.dirname(path)
        date = os.path.basename(day_dir)
        records.append(make_record(date, extract_title(day_dir, text), path))
    return records


if __name__ == "__main__":
    g = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GLOB
    index = build_index(g)
    dest = Path(__file__).with_name("index.jsonl")
    with dest.open("w", encoding="utf-8") as fh:
        for rec in index:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    n_c = sum(1 for r in index if r["type"] == "C")
    print(f"index.jsonl: {len(index)}편 (C={n_c}, unconfirmed={len(index) - n_c})")
