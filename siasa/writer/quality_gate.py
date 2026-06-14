"""시사베테랑 품질 게이트 — 현행 39편 대비 스타일 A/B 리포트(발행 전 사람 go/no-go).

설계 원칙(numeric_gate/script_guard와 동일): **측정·표면화 ≠ 판정**.
- 구조 게이트(script_guard)가 못 잡는 스타일 축만 본다.
- deviation 플래그 = 문장길이(avg/max) + blocklist(신뢰도저하) + 클로징. (advisor 정제)
- 밀도/문단/길이 = surface(사람 검수용, 플래그 아님). 밀도는 가장 깨끗한 분리자이나
  처방(수치 더 써라)=fabrication↑라 자동 act 불가 → 표면화만.
- verdict는 항상 REVIEW. blocklist hit은 high-severity 신호이나 자동 BLOCK 안 함
  (실제 발행본 2026-05-26도 본문 위반 보유 → hard-block은 ground truth 왜곡).

순수 함수 — 추론 백엔드 독립. baseline_profile.json은 baseline_profile.py가 생성.
"""
from __future__ import annotations

import json
import re
import statistics as _st
from pathlib import Path
from typing import Any

from numeric_gate import extract_numeric_claims, split_sentences
from script_guard import CLOSING, CLOSING_PENULT

# 플래그 대상(편차 시 deviation) vs surface(정보 표면화만)
FLAG_FEATURES = ("avg_slen", "max_slen")
SURFACE_FEATURES = ("num_per_1k", "n_para", "chars")

# REFERENCE_writing_system.md §금지 — 신뢰도 저하/가르치는 톤 표현
BLOCKLIST = (
    "전문가는 아닙니다",
    "전문가가 아닙니다",
    "확신이 없습니다",
    "확신은 없습니다",
    "긴장됩니다",
    "주의할 점도 같이 말씀드립니다",
    "알려드리겠습니다",
)

_PARA_SPLIT = re.compile(r"\n\s*\n")
_DEFAULT_PROFILE = Path(__file__).with_name("baseline_profile.json")

# 클로징 면책 제외 윈도(penult 직전 N자). 실측 캘리브레이션: 의식 면책 "전문가는 아닙니다"는
# penult로부터 62~83자에 일정하게 위치, 본문 위반은 343자 이상 → 200자가 클린 분리(83<200<343).
# 트레이드오프: 마지막 200자(클로징 구역)의 신뢰도저하는 의식으로 간주(사람이 클로징은 어차피 정독).
_DISCLAIMER_WINDOW = 200


def extract_style_features(text: str) -> dict[str, Any]:
    """결정론 스타일 피처 — baseline_profile.py와 동일 정의."""
    sents = split_sentences(text)
    slens = [len(s) for s in sents]
    paras = [p for p in _PARA_SPLIT.split(text) if p.strip()]
    n_num = len(extract_numeric_claims(text))
    chars = len(text)
    return {
        "chars": chars,
        "n_sent": len(sents),
        "avg_slen": round(_st.mean(slens), 1) if slens else 0.0,
        "max_slen": max(slens) if slens else 0,
        "n_para": len(paras),
        "n_num": n_num,
        "num_per_1k": round(n_num / (chars / 1000), 1) if chars else 0.0,
    }


def _band(profile: dict[str, Any], feat: str) -> tuple[float, float] | None:
    band = profile.get("features", {}).get(feat)
    if not band:
        return None
    return band["p10"], band["p90"]


def compare_to_baseline(features: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """문장길이 축만 deviation 플래그 — **high-side만**(p90 초과).

    짧은 문장은 이 채널의 house style(TTS 호흡·쉬운말)이라 우려 아님. 품질 결함 방향은
    오직 '문장이 길어짐'(실측 생성 결함 40 vs 베이스 32)이므로 v>p90일 때만 플래그한다.
    """
    flags: list[dict[str, Any]] = []
    for feat in FLAG_FEATURES:
        band = _band(profile, feat)
        if band is None:
            continue
        lo, hi = band
        v = features[feat]
        if v > hi:
            flags.append({
                "axis": feat,
                "value": v,
                "expected": [lo, hi],
                "direction": "high",
                "severity": "med",
            })
    return flags


def surface_metrics(features: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """밀도/문단/길이 — 플래그 아님, 사람 검수용 비교값."""
    out: list[dict[str, Any]] = []
    for feat in SURFACE_FEATURES:
        band = _band(profile, feat)
        v = features[feat]
        entry: dict[str, Any] = {"axis": feat, "value": v}
        if band is not None:
            entry["expected"] = [band[0], band[1]]
            entry["within"] = band[0] <= v <= band[1]
        out.append(entry)
    return out


def _disclaimer_zone_start(text: str) -> int:
    """클로징 면책 구역 시작 오프셋 — penult로부터 _DISCLAIMER_WINDOW 이내는 의식 면책으로 간주.

    실측: 표준 의식 면책("전문가는 아닙니다")은 penult 62~83자 앞에 일정하게 위치(22/39편).
    본문 위반(2026-05-23/26)은 343자 이상 앞 → 거리로 클린 분리. penult 미존재 시 fail-open.
    """
    anchor = text.find(CLOSING_PENULT)
    if anchor == -1:
        anchor = text.find(CLOSING)
    if anchor == -1:
        return len(text) + 1                  # 제외 구역 없음(본문 전수 검사)
    return anchor - _DISCLAIMER_WINDOW


def blocklist_violations(text: str) -> list[dict[str, Any]]:
    """신뢰도저하/금지표현 hit — 클로징 면책 구역 제외(경험적 확정)."""
    zone = _disclaimer_zone_start(text)
    hits: list[dict[str, Any]] = []
    for phrase in BLOCKLIST:
        for m in re.finditer(re.escape(phrase), text):
            if m.start() >= zone:              # 면책/클로징 구역은 정당 → 스킵
                continue
            ctx = text[max(0, m.start() - 25): m.start() + len(phrase) + 15]
            hits.append({
                "phrase": phrase,
                "pos": m.start(),
                "context": ctx.replace("\n", " ").strip(),
                "severity": "high",
            })
    return sorted(hits, key=lambda h: h["pos"])


def closing_check(text: str) -> dict[str, Any]:
    """클로징 의식 정확성(script_guard 상수와 정합)."""
    has_closing = CLOSING in text
    has_penult = CLOSING_PENULT in text
    return {"has_closing": has_closing, "has_penult": has_penult,
            "ok": has_closing and has_penult}


def load_baseline_profile(path: str | Path | None = None) -> dict[str, Any]:
    """동결된 baseline_profile.json 로드(없으면 빈 프로파일 → 플래그 비활성)."""
    p = Path(path) if path else _DEFAULT_PROFILE
    if not p.exists():
        return {"n_samples": 0, "features": {}}
    loaded: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return loaded


def format_quality(q: dict[str, Any]) -> str:
    """품질 A/B 리포트 텍스트(.review.txt 사이드카용). 순수 stdlib — call_writer 복사본과 동일 포맷.

    verdict는 항상 REVIEW(자동 판정 아님). 플래그=문장길이/클로징, 신뢰도저하=본문 위반(제거),
    참고지표=밀도/문단/길이(사람 판단용).
    """
    f = q.get("features", {})
    lines = [
        "=" * 60,
        f"품질 게이트 — 현행 발행본 {q.get('baseline_n', 0)}편 대비 스타일 A/B",
        f"(verdict={q.get('verdict', 'REVIEW')} · 자동 PASS/FAIL 아님 · 발행 판단은 사람)",
        "=" * 60,
        f"분량 {f.get('chars')}자 · 문장 {f.get('n_sent')}개 · 평균문장 {f.get('avg_slen')}자 "
        f"· 최대문장 {f.get('max_slen')}자 · 수치 {f.get('n_num')}개",
    ]
    flags = q.get("flags", [])
    if flags:
        lines.append("\n[편차 플래그] (베이스라인 분포 밖 — 검토 권장)")
        for fl in flags:
            if fl.get("axis") == "closing":
                lines.append(f"  ! 클로징 의식 불완전: {fl.get('value')}")
            else:
                lines.append(f"  ! {fl['axis']}={fl['value']} (기대 {fl['expected']}, {fl['direction']})")
    else:
        lines.append("\n[편차 플래그] 없음")
    blocks = q.get("blocklist", [])
    if blocks:
        lines.append("\n[신뢰도저하 표현] (지침 금지 · 본문 위반 · 발행 전 제거)")
        for b in blocks:
            lines.append(f"  x '{b['phrase']}' … {b['context']}")
    else:
        lines.append("\n[신뢰도저하 표현] 없음")
    surf = q.get("surface", [])
    if surf:
        lines.append("\n[참고 지표] (플래그 아님 · 사람 판단용)")
        for s in surf:
            exp = f" 기대{s['expected']}" if "expected" in s else ""
            within = "" if "within" not in s else (" 범위내" if s["within"] else " 범위밖")
            lines.append(f"  - {s['axis']}={s['value']}{exp}{within}")
    return "\n".join(lines)


def quality_review(text: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """발행 전 품질 A/B 리포트. verdict는 항상 REVIEW(자동 PASS/FAIL 안 함)."""
    profile = profile if profile is not None else load_baseline_profile()
    features = extract_style_features(text)
    flags = compare_to_baseline(features, profile)
    closing = closing_check(text)
    if not closing["ok"]:
        flags.append({"axis": "closing", "value": closing, "severity": "high"})
    blocklist = blocklist_violations(text)
    return {
        "verdict": "REVIEW",
        "features": features,
        "flags": flags,
        "surface": surface_metrics(features, profile),
        "blocklist": blocklist,
        "closing": closing,
        "has_blocking_signal": bool(blocklist) or not closing["ok"],
        "baseline_n": profile.get("n_samples", 0),
    }
