"""시사베테랑 대본 수치 게이트 — 발행 전 사람 팩트 검수용 추출/대조.

중요: 이 게이트는 외부 사실을 검증하지 않는다(ground truth 없음). 하는 일은
①출력의 모든 한글 수치를 문장과 함께 추출(human 검수 리스트), ②주입 사실의 carry 검증(정규화),
③주입 사실에 한해 모순 탐지. 통과=수치가 표면화되고 주입값이 살아남음 ≠ 수치가 참.
"""
from __future__ import annotations
import re

# 한글 숫자/소수 구성 문자 (점=소수)
_CORE = r"[영공일이삼사오육칠팔구십백천만억조점]"
_RUN = rf"{_CORE}(?:{_CORE}|\s)*"   # 숫자문자로 시작, 내부 공백 허용(예: 천사 백 오십)
_UNIT = r"(?:원|퍼센트|프로|달러|명|년|개월|분기|배|채|가구|호|평|위|등|세|시간|일|주|월|선|대|포인트)"
# 수치 토큰: (숫자런 + 단위) 또는 (단위 없는 길이>=2 숫자런)
# (?<![가-힣]): 한글 음절 뒤(예: 환율'이') 시작 금지(particle 오접합). 단위 필수(bare런=일반어 오검출)
_CLAIM_RE = re.compile(rf"(?<![가-힣]){_RUN}{_UNIT}")
# 아라비아 수치(연도·퍼센트·금액 등) — 한글숫자만 보던 게이트 갭 보완.
# TTS는 아라비아를 못 읽으므로(예: '1997년') 검수 리스트에 반드시 표면화한다. 단위 옵션(bare '1997'도 매칭).
_ARABIC_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:%|" + _UNIT + r")?")
_WS = re.compile(r"\s+")


def _normalize(s: str) -> str:
    """공백 제거 + 접미(대/선/여/가량/원대) 정리 — carry 대조용."""
    return _WS.sub("", s)


def split_sentences(text: str) -> list[str]:
    """문장 단위 분할(개행·종결부호)."""
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def extract_numeric_claims(text: str) -> list[dict]:
    """모든 수치 표현을 {value, sentence}로 추출(사람 검수 리스트)."""
    claims: list[dict] = []
    for sent in split_sentences(text):
        for m in _CLAIM_RE.finditer(sent):
            tok = _WS.sub(" ", m.group()).strip()
            if len(tok.replace(" ", "")) < 2:        # 단일 글자 잡음 제외
                continue
            claims.append({"value": tok, "sentence": sent})
        for m in _ARABIC_RE.finditer(sent):          # 아라비아 수치도 표면화(TTS 위반 검수)
            tok = _WS.sub(" ", m.group()).strip(", ")  # 후행 콤마/공백 정리
            if tok:
                claims.append({"value": tok, "sentence": sent})
    return claims


def check_carry(text: str, facts: list[str]) -> dict:
    """주입 사실이 출력에 살아남았는지(공백 정규화, 접미 허용 부분일치)."""
    flat = _normalize(text)
    carried, missing = [], []
    for f in facts:
        (carried if _normalize(f) in flat else missing).append(f)
    return {"carried": carried, "missing": missing}


def check_fact_consistency(text: str, fact: str) -> dict:
    """주입 헤드라인 사실에 한해 모순 탐지(같은 단위 다른 값). 일반 '모든 값 일치' 아님.

    fact 예: '천사백오십원'. 같은 단위(원)의 다른 값이 본문에 있으면 후보로 표면화.
    과거/가정 수치도 잡힐 수 있어 '확정 모순'이 아니라 '검수 후보'로 반환.
    """
    unit_m = re.search(_UNIT, fact)
    if not unit_m:
        return {"unit": None, "fact_value": _normalize(fact), "other_values": []}
    unit = unit_m.group()
    fact_norm = _normalize(fact)
    others = set()
    pat = re.compile(rf"(?<![가-힣]){_RUN}{re.escape(unit)}")
    for m in pat.finditer(text):
        v = _normalize(m.group())
        if v != fact_norm:
            others.add(v)
    return {"unit": unit, "fact_value": fact_norm, "other_values": sorted(others)}


def numeric_review(text: str, facts: list[str] | None = None) -> dict:
    """발행 전 수치 검수 리포트. facts=주입한 핵심 수치(없으면 carry/consistency 생략)."""
    facts = facts or []
    claims = extract_numeric_claims(text)
    report = {"total_claims": len(claims), "claims": claims, "facts_supplied": facts}
    if facts:
        report["carry"] = check_carry(text, facts)
        report["consistency"] = [check_fact_consistency(text, f) for f in facts]
    return report
