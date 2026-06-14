"""quality_gate 테스트 — 현행 코퍼스에서 관측된 형태를 literal 픽스처로(마운트 비의존).

설계: 측정·표면화 ≠ 판정. 플래그 = 문장길이 + blocklist + 클로징. 밀도/문단/길이 = surface.
"""
from quality_gate import (
    extract_style_features, compare_to_baseline, blocklist_violations,
    closing_check, quality_review, format_quality, load_baseline_profile,
)

# 단위테스트용 herm: 코퍼스 의존 없이 고정 프로파일(실측 분포 근사)
PROFILE = {"features": {
    "avg_slen":   {"p10": 25.0, "p90": 38.0, "mean": 31.7, "std": 4.0},
    "max_slen":   {"p10": 45.0, "p90": 80.0, "mean": 63.8, "std": 12.0},
    "num_per_1k": {"p10": 4.0,  "p90": 15.0, "mean": 9.1,  "std": 3.0},
    "n_para":     {"p10": 10.0, "p90": 60.0, "mean": 30.2, "std": 15.0},
    "chars":      {"p10": 4000, "p90": 6000, "mean": 4512, "std": 500},
}}

# 베이스라인풍 본문 — 짧은 문장, 한글숫자, 클로징 면책에 "전문가는 아닙니다"
BASELINE_LIKE = (
    "방송국이 무너지고 있다는 이야기, 한 번쯤 들어보셨을 겁니다.\n"
    "지난해 적자만 팔백팔십일억 원을 기록했습니다.\n"
    "광고 매출은 처음으로 일조 원이 무너졌습니다.\n"
    "흑자를 낸 곳은 한 곳뿐입니다.\n"
    "이게 왜 우리한테 중요한 걸까요.\n"
    "정보를 주고받던 방식이 통째로 바뀌고 있다는 신호입니다.\n\n"
    "나는 투자를 오래 해온 사람이지만 전문가는 아닙니다.\n"
    "오늘 한 이야기는 자료를 바탕으로 정리한 것일 뿐입니다.\n\n"
    "나 임한수, 다음에 또 유익한 이야기 가지고 찾아뵙겠습니다.\n"
    "복잡한 세상, 제대로 읽어갑시다."
)


def test_extract_style_features_shape():
    f = extract_style_features(BASELINE_LIKE)
    assert f["chars"] == len(BASELINE_LIKE)
    assert f["n_sent"] >= 6
    assert f["avg_slen"] > 0
    assert f["max_slen"] >= f["avg_slen"]
    assert f["n_num"] >= 2          # 팔백팔십일억 원, 일조 원
    assert f["num_per_1k"] > 0


def test_compare_flags_only_sentence_length():
    # 긴 문장만 있는 텍스트 → avg/max_slen 플래그. 밀도/문단은 flags 아님.
    long_text = (
        "오늘 아침 뉴스에서 이런 숫자를 보셨다면 아마 깜짝 놀라셨을 텐데 사실 이 숫자는 단순히 외환 시장 이야기가 아니라 여러분 주머니에서 직접 나가는 돈과 직결되는 매우 중요한 문제라는 점을 차분하게 정리해서 말씀드리겠습니다.\n"
        "미국 연준이 금리를 어떻게 끌어올렸느냐 하는 거시적인 흐름 속에서 한국만의 특수한 상황이 더해지면서 환율이 빠르게 오른 것인데 이는 결코 우연이라고 볼 수 없는 구조적인 결과였다고 봐야 합니다."
    )
    f = extract_style_features(long_text)
    flags = compare_to_baseline(f, PROFILE)
    axes = {fl["axis"] for fl in flags}
    assert "avg_slen" in axes or "max_slen" in axes
    assert "num_per_1k" not in axes   # 밀도는 절대 플래그 아님
    assert "n_para" not in axes


def test_baseline_like_minimal_sentence_flags():
    # 베이스라인풍(짧은 문장)은 문장길이 플래그가 없어야
    f = extract_style_features(BASELINE_LIKE)
    flags = compare_to_baseline(f, PROFILE)
    axes = {fl["axis"] for fl in flags}
    assert "avg_slen" not in axes
    assert "max_slen" not in axes


def test_blocklist_excludes_closing_disclaimer():
    # "전문가는 아닙니다"가 penult 직전 클로징 면책 문단에 있으면 위반 아님
    hits = blocklist_violations(BASELINE_LIKE)
    phrases = {h["phrase"] for h in hits}
    assert "전문가는 아닙니다" not in phrases
    assert hits == []


def test_blocklist_detects_body_violation():
    # 2026-05-26 실제 미스 재현: 본문(클로징 면책 아님)에 신뢰도저하 클러스터.
    # 실제처럼 위반 이후 본문이 더 이어지고 표준 면책+의식이 뒤에 옴(위반은 penult에서 >200자).
    text = (
        "시장이 에너지 섹터를 안전판처럼 보고 있다는 신호입니다.\n\n"
        "여기서 주의할 점도 같이 말씀드립니다.\n"
        "저는 투자 전문가는 아닙니다.\n"
        "이런 장에서는 솔직히 긴장됩니다.\n\n"
        "다만 시장 흐름은 분명히 한 방향을 가리키고 있습니다.\n"
        "에너지 섹터로 자금이 이동하는 흐름은 당분간 이어질 가능성이 큽니다.\n"
        "변동성이 큰 종목은 비중과 진입 시점을 신중하게 봐야 합니다.\n"
        "수주 잔고가 탄탄한 기업인지 먼저 확인하는 것이 안전합니다.\n"
        "단기 테마로 급등한 종목은 한 박자 늦춰서 보는 편이 낫습니다.\n\n"
        "오늘 말씀드린 건 어디까지나 시장 흐름을 정리한 겁니다.\n"
        "구체적인 투자 결정은 본인이 신중하게 판단하셔야 합니다.\n\n"
        "나 임한수, 다음에 또 유익한 이야기 가지고 찾아뵙겠습니다.\n"
        "복잡한 세상, 제대로 읽어갑시다."
    )
    hits = blocklist_violations(text)
    phrases = {h["phrase"] for h in hits}
    assert "전문가는 아닙니다" in phrases       # 본문 위반은 잡힘
    assert "긴장됩니다" in phrases
    assert "주의할 점도 같이 말씀드립니다" in phrases


def test_closing_check_detects_ritual():
    ok = closing_check(BASELINE_LIKE)
    assert ok["has_closing"] is True
    assert ok["has_penult"] is True
    assert ok["ok"] is True

    bad = closing_check("클로징 없는 본문입니다.")
    assert bad["ok"] is False


def test_quality_review_verdict_is_review_not_autofail():
    # 종합 리포트: 판정은 REVIEW(자동 PASS/FAIL 안 함), 구조는 flags/surface/blocklist 분리
    r = quality_review(BASELINE_LIKE, PROFILE)
    assert r["verdict"] == "REVIEW"
    assert "flags" in r and "surface" in r and "blocklist" in r and "closing" in r
    assert isinstance(r["surface"], list)


def test_quality_review_surfaces_density_without_flagging():
    # 저밀도 텍스트: 밀도가 surface엔 뜨되 flags엔 없음
    low_density = "오늘은 큰 그림을 봐야 합니다.\n작은 변화가 모이고 있습니다.\n흐름이 바뀌는 중입니다." * 5
    r = quality_review(low_density, PROFILE)
    flag_axes = {fl["axis"] for fl in r["flags"]}
    surface_axes = {s["axis"] for s in r["surface"]}
    assert "num_per_1k" not in flag_axes
    assert "num_per_1k" in surface_axes


def test_quality_review_flags_missing_closing():
    # 클로징 의식 없는 텍스트 → closing 플래그 + has_blocking_signal
    r = quality_review("클로징 없는 본문입니다. 짧은 문장.", PROFILE)
    axes = {fl["axis"] for fl in r["flags"]}
    assert "closing" in axes
    assert r["closing"]["ok"] is False
    assert r["has_blocking_signal"] is True


def test_blocklist_failopen_without_penult():
    # penult/클로징 부재 → 제외 구역 없음(fail-open) → 본문 위반 전수 검출
    text = "저는 전문가는 아닙니다. 그래도 분석해보겠습니다."
    hits = blocklist_violations(text)
    assert any(h["phrase"] == "전문가는 아닙니다" for h in hits)


def test_load_baseline_profile_missing_returns_empty():
    prof = load_baseline_profile("/nonexistent/baseline_profile.json")
    assert prof["n_samples"] == 0
    assert prof["features"] == {}


def test_format_quality_renders_all_sections():
    # 본문 위반 + 긴 문장 → 리포트에 4개 섹션 + verdict 표기
    text = (
        "저는 전문가는 아닙니다 라고 본문에서 길게 말하면서 이 문장은 베이스라인 분포를 한참 넘는 매우 긴 문장으로 작성되어 평균 문장 길이 편차를 유발하도록 의도적으로 늘려 쓴 문장입니다.\n\n"
        "다른 본문 내용이 이어집니다.\n다른 본문 내용이 이어집니다.\n\n"
        "오늘 말씀드린 건 정리한 겁니다.\n\n"
        "나 임한수, 다음에 또 유익한 이야기 가지고 찾아뵙겠습니다.\n복잡한 세상, 제대로 읽어갑시다."
    )
    out = format_quality(quality_review(text, PROFILE))
    assert "품질 게이트" in out
    assert "verdict=REVIEW" in out
    assert "편차 플래그" in out
    assert "신뢰도저하 표현" in out
    assert "참고 지표" in out


def test_format_quality_clean_report_shows_none_sections():
    out = format_quality(quality_review(BASELINE_LIKE, PROFILE))
    assert "[편차 플래그] 없음" in out
    assert "[신뢰도저하 표현] 없음" in out
