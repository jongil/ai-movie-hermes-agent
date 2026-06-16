"""corpus 인덱스 빌더 테스트 — 순수 함수(title 정리·type 판정·레코드) 단위.

소비자 쿼리: "토픽 유사 과거편 1~2개". 스키마 = {date, title, type, path}.
"""
import unicodedata

import build_corpus_index as bci
from build_corpus_index import (
    clean_title, type_for_date, make_record, extract_title, build_index, _first_sentence,
)


def test_clean_title_strips_noise_suffixes():
    assert clean_title("일본 저출산 정책 전환 분석") == "일본 저출산 정책 전환"
    assert clean_title("서울시장 지지율 분석 가이드라인") == "서울시장 지지율"
    assert clean_title("AI 반도체 설계 자동화 분석 지침") == "AI 반도체 설계 자동화"
    assert clean_title("국민의힘 공천 개혁") == "국민의힘 공천 개혁"  # 접미 없으면 그대로


def test_clean_title_handles_whitespace():
    assert clean_title("  방송국 몰락, 데이터로 본 현황  ") == "방송국 몰락, 데이터로 본 현황"


def test_clean_title_normalizes_nfd_filename():
    # macOS 파일명 회귀: NFD(자모분해) 입력도 접미 제거돼야(NFC 정규화 선행)
    nfd = unicodedata.normalize("NFD", "일본 저출산 정책 전환 분석")
    assert nfd != "일본 저출산 정책 전환 분석"      # 실제로 NFD가 다름을 확인
    assert clean_title(nfd) == "일본 저출산 정책 전환"


def test_type_for_date_may_onward_is_c():
    assert type_for_date("2026-05-01") == "C"   # 사용자 확정: 5월+ 전부 C
    assert type_for_date("2026-06-09") == "C"


def test_type_for_date_april_is_unconfirmed():
    # 04월 현행 컨벤션 시작분은 미확인(B형 의심 제목 존재) — 거짓 라벨 금지
    assert type_for_date("2026-04-13") == "unconfirmed"
    assert type_for_date("2026-04-30") == "unconfirmed"


def test_make_record_shape():
    rec = make_record("2026-05-01", "방송국 몰락, 데이터로 본 현황",
                       "/x/2026-05-01/대본.txt")
    assert rec == {
        "date": "2026-05-01",
        "title": "방송국 몰락, 데이터로 본 현황",
        "type": "C",
        "path": "/x/2026-05-01/대본.txt",
    }


def test_first_sentence_splits_on_terminator():
    assert _first_sentence("환율이 올랐습니다. 그 다음 문장.") == "환율이 올랐습니다"
    assert _first_sentence("종결부호 없는 긴 도입부 텍스트") == "종결부호 없는 긴 도입부 텍스트"


def test_extract_title_prefers_docx(tmp_path):
    day = tmp_path / "2026-05-01"
    (day / "docs").mkdir(parents=True)
    (day / "docs" / "방송국 몰락 분석.docx").write_text("", encoding="utf-8")
    assert extract_title(str(day), "대본 첫 문장입니다.") == "방송국 몰락"  # docx 우선 + 접미 제거


def test_extract_title_fallback_when_no_docx(tmp_path):
    day = tmp_path / "2026-06-01"
    day.mkdir()
    assert extract_title(str(day), "사전투표 줄이 길었습니다. 둘째 문장.") == "사전투표 줄이 길었습니다"


def test_build_index_filters_nonpublishable(tmp_path, monkeypatch):
    # is_publishable을 모킹해 글로빙·필터·정렬·레코드 빌드만 검증(거대 픽스처 회피)
    for d, ok in [("2026-05-02", True), ("2026-05-01", True), ("2026-03-01", False)]:
        day = tmp_path / d
        day.mkdir()
        (day / "대본.txt").write_text(f"{d} 본문. 끝.", encoding="utf-8")
    monkeypatch.setattr(bci, "is_publishable", lambda t: "2026-03" not in t)
    recs = build_index(str(tmp_path / "2026-*" / "대본.txt"))
    dates = [r["date"] for r in recs]
    assert dates == ["2026-05-01", "2026-05-02"]      # 정렬 + 구포맷(03월) 제외
    assert all(r["type"] == "C" for r in recs)
