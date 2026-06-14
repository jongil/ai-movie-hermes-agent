"""script_guard 단위 테스트 (AAA 패턴)."""
from script_guard import (
    detect_degenerate, finalize_script, is_publishable, format_violations, CLOSING,
)

import os
_FIX = os.path.join(os.path.dirname(__file__), "fixture_good.txt")
GOOD = open(_FIX, encoding="utf-8").read().strip()        # 실제 발행된 대본(4214자)
BODY = GOOD.split(CLOSING)[0].strip()                      # 클로징 없는 본문


def test_finalize_truncates_after_closing():
    # Arrange: 클로징 뒤에 퇴화 꼬리
    text = GOOD + "\n```\n```\n구십팔째, 같은 문장. 구십구째, 같은 문장."
    # Act
    out = finalize_script(text)
    # Assert: 클로징+마침표에서 끝, 꼬리 제거
    assert out.endswith(CLOSING + ".")
    assert "```" not in out
    assert "구십팔째" not in out


def test_finalize_keeps_period():
    assert finalize_script("본문.\n" + CLOSING + ".").endswith(CLOSING + ".")


def test_finalize_no_closing_returns_cleaned():
    # 클로징 없으면 펜스만 제거하고 보존
    text = "본문 내용입니다.\n```\n```"
    out = finalize_script(text)
    assert "```" not in out
    assert "본문 내용입니다." in out


def test_detect_degenerate_consecutive_lines():
    text = "다른 줄.\n같은 줄.\n같은 줄.\n같은 줄."
    assert detect_degenerate(text) is True


def test_detect_degenerate_window_repeat():
    text = "경상수지적자가지속되고있습니다환율하락기대난" * 6  # 22자×6, k-gram 빈도>=5
    assert detect_degenerate(text) is True


def test_detect_non_degenerate():
    text = "첫째 문장입니다. 둘째 문장은 다릅니다. 셋째 문장도 또 다릅니다."
    assert detect_degenerate(text) is False


def test_is_publishable_good():
    assert is_publishable(GOOD) is True


def test_is_publishable_no_closing():
    assert is_publishable(BODY) is False


def test_is_publishable_too_short():
    assert is_publishable("짧은 글.\n" + CLOSING + ".") is False


def test_is_publishable_degenerate_rejected():
    bad = BODY + "\n같은 줄.\n같은 줄.\n같은 줄.\n" + CLOSING + "."
    assert is_publishable(bad) is False


def test_format_violations_flags_arabic_and_fence():
    issues = format_violations("매출이 100억입니다.\n```\n")
    assert "arabic_digit" in issues
    assert "code_fence" in issues


def test_format_violations_clean():
    assert format_violations("매출이 백억입니다. 한글로만 씁니다.") == []


from script_guard import ensure_closing, needs_retry, CLOSING_RITUAL


def test_ensure_closing_appends_when_missing():
    # Arrange: 클로징 없이 끝난 본문
    text = BODY  # 4000자+ 본문, 클로징 없음
    # Act
    out = ensure_closing(text)
    # Assert: 불변 의식이 끝에 붙고 penult 중복 없음
    assert out.rstrip(".").endswith(CLOSING)
    assert out.count("나 임한수, 다음에 또 유익한 이야기 가지고 찾아뵙겠습니다.") == 1


def test_ensure_closing_truncates_when_present():
    # 이미 클로징 있고 뒤에 잡음 → 절단(중복 부착 안 함)
    text = BODY + "\n" + CLOSING_RITUAL + "\n```\n잡음"
    out = ensure_closing(text)
    assert out.count(CLOSING) == 1
    assert out.rstrip(".").endswith(CLOSING)
    assert "잡음" not in out


def test_needs_retry_short_body():
    # 본문이 짧으면(클로징만으론 길이 못 채움) 재시도
    assert needs_retry("짧은 본문.\n" + CLOSING_RITUAL) is True


def test_needs_retry_ok_when_long_body():
    assert needs_retry(GOOD) is False


def test_needs_retry_degenerate():
    bad = BODY + "\n같은 줄.\n같은 줄.\n같은 줄."
    assert needs_retry(bad) is True


from script_guard import strip_closing_tail


def test_strip_closing_tail_removes_ritual():
    text = BODY + "\n" + CLOSING_RITUAL
    out = strip_closing_tail(text)
    assert CLOSING not in out
    assert "나 임한수, 다음에 또 유익한 이야기 가지고 찾아뵙겠습니다." not in out
    assert len(out) > 0 and text.startswith(out)  # 본문 앞부분 보존


def test_strip_closing_tail_no_closing_passthrough():
    text = "본문만 있습니다. 클로징 없음."
    assert strip_closing_tail(text) == text


def test_finalize_strips_mojibake():
    text = "흐름 속에 � 중요한 변화입니다.\n" + CLOSING + "."
    out = finalize_script(text)
    assert "�" not in out


def test_ensure_closing_strips_paraphrased_signoff():
    # 모델 자체 마무리(패러프레이즈) + 감사합니다 → 제거 후 정식 의식만
    text = (BODY + "\n저는 다음에 또 유익한 이야기를 가지고 찾아뵙겠습니다.\n감사합니다.")
    out = ensure_closing(text)
    assert out.count("찾아뵙겠") == 1               # 정식 1회만
    assert "감사합니다" not in out.split("나 임한수")[0][-50:]  # 직전 감사합니다 제거
    assert out.rstrip(".").endswith(CLOSING)
