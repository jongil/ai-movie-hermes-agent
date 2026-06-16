"""siasa_writer 단위 테스트 — 프롬프트 구성·선택 로직(모델 비의존)."""
from siasa_writer import build_user_prompt, pick_best, OUTLINE, CLOSE, SYSTEM, SLEN_GUIDE
import script_guard as g

BODY = open(__file__.replace("test_siasa_writer.py", "fixture_good.txt"), encoding="utf-8").read()
BODY = BODY.split(CLOSE)[0].strip()


def test_prompt_contains_all_sections():
    p = build_user_prompt("환율 급등")
    for i in range(1, len(OUTLINE) + 1):
        assert f"{i})" in p
    assert "주제: 환율 급등" in p
    assert "사천오백자 이상" in p


def test_sentence_length_guide_in_system():
    # 스파이크 GO(avg_slen 43.8→35.5)로 검증된 문장길이 레버가 SYSTEM에 반영
    assert SLEN_GUIDE in SYSTEM
    assert "짧고 단정" in SLEN_GUIDE


def test_sentence_length_guide_in_user_prompt():
    # 검증된 treatment는 system+user 양쪽에 지침 주입 → user 프롬프트에도 반영
    assert SLEN_GUIDE in build_user_prompt("환율 급등")


def test_pick_best_prefers_publishable_longest():
    short = "짧다.\n" + g.CLOSING_RITUAL
    longp = BODY + "\n" + g.CLOSING_RITUAL          # 발행가능(길고 형식 OK)
    chosen, ok = pick_best([short, longp])
    assert ok is True
    assert chosen.count(CLOSE) == 1
    assert len(chosen) > len(short)


def test_pick_best_appends_closing_when_missing():
    chosen, _ = pick_best([BODY])  # 클로징 없는 본문
    assert CLOSE in chosen
