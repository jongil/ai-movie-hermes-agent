"""numeric_gate 테스트 — 실제 T0/T1/T2 샘플의 수치 형태를 픽스처로."""
from numeric_gate import (
    extract_numeric_claims, check_carry, check_fact_consistency, numeric_review, _normalize,
)

# 실제 샘플에서 관측된 형태들
REAL = (
    "원달러 환율이 천사 백 오십 원 선을 넘었습니다.\n"          # 공백 분할
    "지난해 누적 적자가 육백칠십억 달러를 넘어섰습니다.\n"
    "합계출산율은 영점육팔명입니다.\n"
    "상승률이 팔점일퍼센트에 달했습니다.\n"
    "잔금 비율이 육십팔점육퍼센트로 높았습니다.\n"
    "이천삼십칠년에 기금이 바닥납니다."
)


def test_extract_finds_spaced_and_decimal_and_unit_forms():
    vals = [c["value"].replace(" ", "") for c in extract_numeric_claims(REAL)]
    assert "천사백오십원" in vals          # 공백 형태 정규화 매칭
    assert "육백칠십억달러" in vals
    assert "영점육팔명" in vals             # 소수+명
    assert "팔점일퍼센트" in vals
    assert "육십팔점육퍼센트" in vals
    assert "이천삼십칠년" in vals


def test_each_claim_carries_its_sentence():
    claims = extract_numeric_claims(REAL)
    pct = next(c for c in claims if "팔점일퍼센트" in c["value"].replace(" ", ""))
    assert "상승률" in pct["sentence"]


def test_carry_normalizes_spaces_and_suffix():
    # 주입 '천사백오십원' vs 출력 '천사 백 오십 원대' → carry 성공으로 봐야 함
    text = "환율이 천사 백 오십 원대까지 올랐습니다."
    r = check_carry(text, ["천사백오십원"])
    assert r["carried"] == ["천사백오십원"]
    assert r["missing"] == []


def test_carry_detects_genuine_miss():
    # T0 실패 재현: 주제는 천사백오십인데 본문은 천삼백팔십
    text = "환율이 천삼백팔십원대까지 치솟았습니다."
    r = check_carry(text, ["천사백오십원"])
    assert r["missing"] == ["천사백오십원"]


def test_consistency_anchors_to_fact_only():
    # 헤드라인 천사백오십원인데 본문에 천삼백팔십원/천사백육원 혼재 → 후보로 표면화
    text = "천사백오십원을 넘었지만 어제는 천삼백팔십원, 가정상 천사백육원."
    r = check_fact_consistency(text, "천사백오십원")
    assert r["unit"] == "원"
    assert "천삼백팔십원" in r["other_values"]
    assert "천사백육원" in r["other_values"]
    assert "천사백오십원" not in r["other_values"]   # fact 자신은 제외


def test_review_without_facts_skips_carry():
    r = numeric_review(REAL)
    assert r["total_claims"] > 0
    assert "carry" not in r


def test_no_false_positive_common_words():
    # 구조(9조)·사이(4,2)·일이(1,2) 같은 일반어는 단위 없으니 추출 안 됨
    text = ("이런 구조가 형성됩니다. 위원들 사이에서 평가가 나옵니다. "
            "원금을 밑도는 일이 있습니다. 환율은 천사백오십원입니다.")
    vals = [c["value"].replace(" ", "") for c in extract_numeric_claims(text)]
    assert "구조" not in vals
    assert "사이" not in vals
    assert "일이" not in vals
    assert "천사백오십원" in vals   # 진짜 수치는 유지


# --- 아라비아숫자 가시화 (Fix A: 게이트 갭) ---
# TTS는 아라비아를 못 읽음. 한글숫자만 추출하면 '1997년 IMF' 같은 값이 검수 리스트에
# 안 떠 두 가드를 다 통과(구멍). 아라비아 수치도 표면화해 사람이 검수/교체하게 한다.

def test_extract_finds_arabic_year():
    # 게이트 갭 재현: 아라비아 연도가 .review.txt에 떠야 한다.
    text = "1997년 IMF 외환위기 당시 큰 충격이 있었습니다."
    vals = [c["value"] for c in extract_numeric_claims(text)]
    assert any("1997" in v for v in vals)


def test_extract_finds_arabic_percent_and_unit():
    text = "상승률이 8.1%에 달했고 기준금리는 3%입니다."
    vals = [c["value"] for c in extract_numeric_claims(text)]
    assert any("8.1" in v for v in vals)
    assert any(v.startswith("3") for v in vals)   # 3 또는 3%


def test_arabic_comma_adjacent_behavior():
    # 콤마 인접 동작을 '결정'으로 고정(사고 아님): 공백 분리 + 후행 콤마 제거.
    text = "2024, 2025년에 변화가 있었습니다."
    vals = [c["value"] for c in extract_numeric_claims(text)]
    assert "2024" in vals                          # 후행 콤마 제거됨
    assert any("2025" in v for v in vals)          # 2025년


def test_korean_and_arabic_coexist():
    text = "환율은 천사백오십원인데 1997년과 비교됩니다."
    vals = [c["value"].replace(" ", "") for c in extract_numeric_claims(text)]
    assert "천사백오십원" in vals                   # 한글 추출 회귀 없음
    assert any("1997" in v for v in vals)          # 아라비아도 함께
