"""시사베테랑 대본 후처리 가드 — 결정론적 안전망(클로징 절단·퇴화/형식 검사).

파인튜닝은 형식을 학습했지만 샘플링 변동으로 분량/종료/퇴화가 불안정하다.
이 모듈은 생성 산출물을 발행 가능 형태로 다듬고(finalize), 발행 가능 여부를 판정한다(is_publishable).
순수 함수 — 추론 백엔드(transformers/Ollama)와 독립. 재시도 루프는 호출측이 담당.
"""
from __future__ import annotations
import re
from collections import Counter

CLOSING = "복잡한 세상, 제대로 읽어갑시다"
# 39/39 대본 불변 마무리 의식 — 모델 의존 없이 결정론적으로 부착
CLOSING_PENULT = "나 임한수, 다음에 또 유익한 이야기 가지고 찾아뵙겠습니다."
CLOSING_RITUAL = CLOSING_PENULT + "\n" + "복잡한 세상, 제대로 읽어갑시다."
MIN_LEN = 3000
MAX_LEN = 7000
FENCE_RE = re.compile(r"^\s*```.*$", re.MULTILINE)
HEADER_RE = re.compile(r"(?m)^\s{0,3}#")
ARABIC_RE = re.compile(r"[0-9]")


def detect_degenerate(text: str) -> bool:
    """퇴화 감지: 연속 동일 줄 3회+ 또는 40자 윈도 4회+ 반복."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    run = 1
    for i in range(1, len(lines)):
        run = run + 1 if lines[i] == lines[i - 1] else 1
        if run >= 3:
            return True
    k = 20
    if len(text) > k:
        grams = Counter(text[i : i + k] for i in range(len(text) - k + 1))
        if grams.most_common(1)[0][1] >= 5:
            return True
    return False


def finalize_script(text: str, closing: str = CLOSING) -> str:
    """클로징 첫 등장 직후(문장부호 포함)에서 절단하고 코드펜스 줄을 제거.

    클로징 미존재 시 펜스만 제거하고 그대로 반환(호출측이 재시도 판단).
    """
    cleaned = FENCE_RE.sub("", text).replace("\ufffd", "").strip()
    idx = cleaned.find(closing)
    if idx == -1:
        return cleaned
    end = idx + len(closing)
    tail = cleaned[end : end + 2]
    if tail[:1] in (".", "。", "!", "?"):
        end += 1
    return cleaned[:end].strip()


_SIGNOFF_RE = re.compile(r"(찾아뵙겠|읽어갑시다)|^\s*감사합니다[.!]?\s*$")


def ensure_closing(text: str) -> str:
    """기존 클로징/사인오프(정식·패러프레이즈)를 모두 벗기고 불변 2줄 의식 1회만 재부착.

    클로징은 고정 의식이므로 모델 산출과 무관하게 결정론적으로 정확히 1회 보장한다.
    조기 반환 없이 항상 재구성 → 이중 사인오프(모델 자체 마무리 + 정식)도 단일화.
    """
    body = strip_closing_tail(text)               # 정식 클로징·penult·펜스·mojibake 제거
    lines = body.rstrip().splitlines()
    while lines and _SIGNOFF_RE.search(lines[-1]):  # 패러프레이즈 사인오프 제거
        lines.pop()
    body = "\n".join(lines).rstrip()
    return (body + "\n\n" + CLOSING_RITUAL).strip()


def needs_retry(text: str, min_body: int = 3000) -> bool:
    """재생성 필요 신호: 본문(클로징 제외)이 너무 짧거나 퇴화.

    클로징 부착은 길이를 못 채우므로, 본문 자체가 부실하면 재시도해야 한다.
    """
    body = text.split(CLOSING)[0] if CLOSING in text else text
    if len(body.strip()) < min_body:
        return True
    if detect_degenerate(text):
        return True
    return False


def strip_closing_tail(text: str) -> str:
    """이어쓰기용: 클로징/penult 의식을 본문에서 제거하고 순수 본문만 반환.

    finalize_script가 '클로징 직후 절단(유지)'인 반면, 이것은 '클로징 제거'다.
    """
    cleaned = FENCE_RE.sub("", text).replace("\ufffd", "").strip()
    idx = cleaned.find(CLOSING)
    if idx != -1:
        cleaned = cleaned[:idx]
    lines = cleaned.rstrip().splitlines()
    while lines and lines[-1].strip() == CLOSING_PENULT:
        lines.pop()
    return "\n".join(lines).rstrip()


def format_violations(text: str) -> list[str]:
    """형식 위반 목록(보고용) — 빈 리스트 = 형식 통과."""
    issues: list[str] = []
    if ARABIC_RE.search(text):
        issues.append("arabic_digit")
    if HEADER_RE.search(text):
        issues.append("markdown_header")
    if "```" in text:
        issues.append("code_fence")
    return issues


def is_publishable(text: str, min_len: int = MIN_LEN, max_len: int = MAX_LEN) -> bool:
    """발행 가능 = 클로징 1회+ · 길이 범위 · 비퇴화 · 펜스/헤더 없음."""
    if text.count(CLOSING) < 1:
        return False
    if not (min_len <= len(text) <= max_len):
        return False
    if detect_degenerate(text):
        return False
    if "```" in text or HEADER_RE.search(text):
        return False
    return True
