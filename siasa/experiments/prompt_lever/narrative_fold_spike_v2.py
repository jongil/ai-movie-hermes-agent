#!/usr/bin/env python3
"""Gate B 재시도(v2) — 서사 fold 문구 약화 + 시드 확대 + 발행실패 원인 기록.

v1 NO-GO 진단: pub 3→2는 품질붕괴가 아니라 seed 7 chars=7071 > MAX_LEN(7000) = 길이 1% 오버플로.
A2(구체성)가 분량을 약간 밀어올려 1편이 캡 초과. → 가설: 문구 약화로 해소.

변경(사용자 지시):
  ① 문구 약화 — A1/A2를 짧게, **SYSTEM 1곳만** 주입(v1은 system+user 양쪽).
  ② 시드셋 확대 — 3→6(발행성 하락이 노이즈 vs 신호인지 분리).
  ③ (보강) 발행실패 원인 기록 — too_long/degenerate/no_closing 등 분류.

baseline(control)=현행 deployed SYSTEM/build_user_prompt(SLEN_GUIDE 포함). treatment=control+짧은 FOLD(system만).
사전등록 게이트(rate 기반): B-1 회귀 필수 / B-2 서사프록시 보조 / B-3 후킹 사람검수.

실행(서버, gateway 컨테이너):
  docker cp .../narrative_fold_spike_v2.py <gateway>:/tmp/spikeB2.py && docker exec <gateway> python /tmp/spikeB2.py
GPU 안전: 각 팔 gpu_lock 직렬화.
"""
from __future__ import annotations

import statistics as st
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/gateway/siasa")

import httpx  # noqa: E402

import quality_gate  # noqa: E402
import script_guard  # noqa: E402
import siasa_writer  # noqa: E402
from gateway.config import get_settings  # noqa: E402
from gateway.queue.connection import get_redis  # noqa: E402
from gateway.queue.gpu_lock import WRITER_LEASE_SECONDS, gpu_lock  # noqa: E402

TOPIC = "인공지능 규제와 일자리 충격"
SEEDS = [11, 42, 7, 3, 99, 23]  # v1 3개 + 신규 3개 (n=6, 노이즈/신호 분리)
MAX_NEW = 5200  # baseline과 동일(분량예산 변경=교란이므로 고정)

# === 약화 문구(짧게, SYSTEM 1곳만) ===
GUIDE_A1 = "이 대본의 주인공은 시청자입니다. 임한수는 곁에서 길을 짚어 주는 안내자입니다."
GUIDE_A2 = "막연한 표현 대신 고유명사와 구체 수치로 씁니다."
FOLD = GUIDE_A1 + " " + GUIDE_A2  # v1 ~190자 → v2 ~50자

OPENING_WINDOW = 250
VIEWER_TOKENS = ["여러분", "당신", "우리", "본인", "시청자"]

B1_AVG_MAX = 37.0
B1_AVG_DRIFT = 2.0
B1_MAX_DRIFT = 10
B1_NUM_DROP = 1.0


def build_arms(topic: str) -> tuple[dict[str, str], dict[str, str]]:
    base_sys = siasa_writer.SYSTEM
    base_user = siasa_writer.build_user_prompt(topic)
    control = {"system": base_sys, "user": base_user}
    treatment = {"system": base_sys + " " + FOLD, "user": base_user}  # user 무변경(1곳만)
    return control, treatment


def generate(settings, prompt: dict[str, str], redis) -> list[str]:
    payload = {"system": prompt["system"], "user": prompt["user"],
               "seeds": SEEDS, "max_new_tokens": MAX_NEW}
    with gpu_lock(redis, lease_seconds=WRITER_LEASE_SECONDS, wait_seconds=180):
        resp = httpx.post(f"{settings.writer_url}/generate", json=payload,
                          timeout=WRITER_LEASE_SECONDS)
        resp.raise_for_status()
        data = resp.json()
    if not data.get("candidates"):
        raise RuntimeError(f"no candidates: {str(data.get('error'))[:400]}")
    return data["candidates"]


def _pub_fail(text: str) -> str:
    """is_publishable 실패 원인 분류(빈 문자열=발행가능)."""
    if text.count(script_guard.CLOSING) < 1:
        return "no_closing"
    if len(text) < script_guard.MIN_LEN:
        return "too_short"
    if len(text) > script_guard.MAX_LEN:
        return "too_long"
    if script_guard.detect_degenerate(text):
        return "degenerate"
    if "```" in text or script_guard.HEADER_RE.search(text):
        return "fence_or_header"
    return ""


def _opening_connect(text: str) -> bool:
    return any(tok in text[:OPENING_WINDOW] for tok in VIEWER_TOKENS)


def measure(cands: list[str]) -> list[dict]:
    rows = []
    for c in cands:
        final = script_guard.ensure_closing(c)
        q = quality_gate.quality_review(final)
        f = q["features"]
        rows.append({
            "avg_slen": f["avg_slen"], "max_slen": f["max_slen"], "chars": f["chars"],
            "num_per_1k": f["num_per_1k"], "closing_ok": q["closing"]["ok"],
            "blocklist": len(q["blocklist"]),
            "publishable": script_guard.is_publishable(final),
            "pub_fail": _pub_fail(final),
            "open_connect": _opening_connect(final),
            "head": final[:120].replace("\n", " "),
        })
    return rows


def _mean(rows: list[dict], k: str) -> float:
    vals = [r[k] for r in rows]
    return round(st.mean(vals), 1) if vals else 0.0


def _print_arm(name: str, rows: list[dict]) -> None:
    print(f"\n[{name}] n={len(rows)}")
    print(f"  {'seed':>5} {'avg_slen':>9} {'max_slen':>9} {'chars':>6} "
          f"{'num/1k':>7} {'close':>6} {'pub':>5} {'fail':>10} {'open↔':>6}")
    for sd, r in zip(SEEDS, rows):
        print(f"  {sd:>5} {r['avg_slen']:>9} {r['max_slen']:>9} {r['chars']:>6} "
              f"{r['num_per_1k']:>7} {str(r['closing_ok']):>6} {str(r['publishable']):>5} "
              f"{(r['pub_fail'] or '-'):>10} {str(r['open_connect']):>6}")
    print(f"  {'MEAN':>5} {_mean(rows, 'avg_slen'):>9} {_mean(rows, 'max_slen'):>9} "
          f"{_mean(rows, 'chars'):>6} {_mean(rows, 'num_per_1k'):>7}")


def _print_heads(name: str, rows: list[dict]) -> None:
    print(f"\n--- {name} 도입부(사람 검수용, B-3) ---")
    for sd, r in zip(SEEDS, rows):
        print(f"  [seed {sd}] {r['head']}")


def verdict(c_rows: list[dict], t_rows: list[dict]) -> None:
    n = len(t_rows)
    c_avg, t_avg = _mean(c_rows, "avg_slen"), _mean(t_rows, "avg_slen")
    c_max, t_max = _mean(c_rows, "max_slen"), _mean(t_rows, "max_slen")
    c_num, t_num = _mean(c_rows, "num_per_1k"), _mean(t_rows, "num_per_1k")
    c_close, t_close = sum(r["closing_ok"] for r in c_rows), sum(r["closing_ok"] for r in t_rows)
    c_pub, t_pub = sum(r["publishable"] for r in c_rows), sum(r["publishable"] for r in t_rows)
    c_block, t_block = sum(r["blocklist"] for r in c_rows), sum(r["blocklist"] for r in t_rows)
    c_conn, t_conn = sum(r["open_connect"] for r in c_rows), sum(r["open_connect"] for r in t_rows)
    t_fails = [r["pub_fail"] for r in t_rows if r["pub_fail"]]

    print("\n" + "=" * 66)
    print(f"control  avg={c_avg} max={c_max} num/1k={c_num} pub={c_pub}/{n} conn={c_conn}/{n}")
    print(f"treatment avg={t_avg} max={t_max} num/1k={t_num} pub={t_pub}/{n} conn={t_conn}/{n}")
    if t_fails:
        print(f"treatment 발행실패 원인: {t_fails}")

    b1 = (
        t_avg <= B1_AVG_MAX and t_avg <= c_avg + B1_AVG_DRIFT
        and t_max <= c_max + B1_MAX_DRIFT
        and t_pub >= c_pub and t_close >= c_close
        and t_block <= c_block and t_num >= c_num - B1_NUM_DROP
    )
    b2 = (t_conn >= c_conn) and (t_num >= c_num - B1_NUM_DROP)

    print("-" * 66)
    print(f"B-1 회귀(필수): {'PASS' if b1 else 'FAIL'} "
          f"(avg {c_avg}->{t_avg}≤{B1_AVG_MAX}, max {c_max}->{t_max}, "
          f"pub {c_pub}->{t_pub}, close {c_close}->{t_close}, block {c_block}->{t_block}, "
          f"num {c_num}->{t_num})")
    print(f"B-2 서사프록시(보조): {'PASS' if b2 else 'FAIL'} (conn {c_conn}->{t_conn}, num {c_num}->{t_num})")
    print("B-3 후킹(사람): 위 도입부 샘플을 금지규칙 후킹 체크리스트로 판정 — 자동 GO 아님")
    print("-" * 66)
    if not b1:
        print("판정: NO-GO(회귀) — 문서만 유지, fold 보류. 발행실패 원인 위 참조.")
    elif not b2:
        print("판정: 조건부 — 회귀 없으나 서사 프록시 미개선. 재설계 검토.")
    else:
        print("판정: 자동 GREEN(B-1·B-2) — B-3 사람검수 통과 시 최종 GO(fold 반영).")
    print("=" * 66)


def main() -> None:
    settings = get_settings()
    redis = get_redis()
    control_p, treat_p = build_arms(TOPIC)
    print(f"TOPIC: {TOPIC} | SEEDS: {SEEDS} (n={len(SEEDS)}) | FOLD({len(FOLD)}자, system만): {FOLD}")
    print("control 생성(현행 deployed)...")
    c_rows = measure(generate(settings, control_p, redis))
    print("treatment 생성(+약화 fold, system 1곳)...")
    t_rows = measure(generate(settings, treat_p, redis))
    _print_arm("control", c_rows)
    _print_arm("treatment", t_rows)
    _print_heads("treatment", t_rows)
    verdict(c_rows, t_rows)


if __name__ == "__main__":
    main()
