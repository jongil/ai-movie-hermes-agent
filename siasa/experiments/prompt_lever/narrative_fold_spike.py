#!/usr/bin/env python3
"""Gate B 스파이크 — ebook 증류 서사 원칙(A1 가이드보이스 + A2 구체성)을 SYSTEM/user에 얹었을 때
2a(문장길이 레버)를 회귀시키지 않고 품질을 유지/개선하는가.

baseline(control) = 현행 deployed SYSTEM/build_user_prompt (SLEN_GUIDE 이미 포함분).
treatment = control + A1 + A2 (system·user 양쪽 주입, 2a에서 검증된 형태).
→ 측정 대상은 "서사 fold의 한계효과"이지 2a 재측정이 아니다(advisor).

사전등록 게이트(plans/20260616-1848-...):
  B-1 회귀(필수): avg_slen 밴드 유지(≤37, control 대비 +2 이내), max 비악화, closing/pub 비감소,
                  blocklist 비증가, num_per_1k 비퇴화(-1.0 이내). → 2a·발행성 보존.
  B-2 서사 프록시(보조, 측정가능분만): 도입부 시청자-연결 표현 존재, num_per_1k(구체성 대리) 비감소.
  B-3 후킹/스토리(사람): 자동 GO 아님 — 도입부 샘플을 출력해 사람이 금지규칙 후킹 체크리스트로 판정.

실행(서버, gateway 컨테이너 내):
  docker cp .../narrative_fold_spike.py <gateway_container>:/tmp/spikeB.py
  docker exec <gateway_container> python /tmp/spikeB.py

GPU 안전: 직접 /generate는 게이트웨이 락 우회 → 각 팔을 gpu_lock으로 직렬화(ComfyUI/Ollama 배타).
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

TOPIC = "인공지능 규제와 일자리 충격"  # 2a와 동일 주제 계열(비교 일관성)
SEEDS = [11, 42, 7]
MAX_NEW = 5200

# === 증류 원칙(작가-원칙.md A1/A2)의 프롬프트 후보 문구 ===
GUIDE_A1 = (
    "이 대본의 주인공은 시청자입니다. 임한수는 주인공이 아니라, 시청자의 자산과 삶을 위해 길을 "
    "짚어 주는 침착한 안내자입니다. 가르치거나 자랑하지 말고, 시청자가 스스로 판단하도록 사실과 통찰만 건넵니다."
)
GUIDE_A2 = (
    "추상적 표현을 피하고 가능한 한 구체적으로 쓰세요. '경제가 나빠졌다' 같은 막연한 말 대신 "
    "고유명사와 구체 수치(한글로)로 적습니다."
)
FOLD = GUIDE_A1 + " " + GUIDE_A2

# 도입부 시청자-연결 프록시(B-2): 첫 구간에 2/1인칭 청자 지시어 존재 여부
OPENING_WINDOW = 250
VIEWER_TOKENS = ["여러분", "당신", "우리", "본인", "시청자"]

# 사전등록 임계
B1_AVG_MAX = 37.0          # 회귀 상한(2a 밴드)
B1_AVG_DRIFT = 2.0         # control 대비 허용 상승
B1_MAX_DRIFT = 10          # max_slen 허용 악화
B1_NUM_DROP = 1.0          # num_per_1k 허용 하락


def build_arms(topic: str) -> tuple[dict[str, str], dict[str, str]]:
    base_sys = siasa_writer.SYSTEM
    base_user = siasa_writer.build_user_prompt(topic)
    control = {"system": base_sys, "user": base_user}
    treatment = {
        "system": base_sys + " " + FOLD,
        "user": base_user + FOLD + "\n",
    }
    return control, treatment


def generate(settings, prompt: dict[str, str], redis) -> list[str]:
    payload = {
        "system": prompt["system"],
        "user": prompt["user"],
        "seeds": SEEDS,
        "max_new_tokens": MAX_NEW,
    }
    with gpu_lock(redis, lease_seconds=WRITER_LEASE_SECONDS, wait_seconds=180):
        resp = httpx.post(
            f"{settings.writer_url}/generate", json=payload, timeout=WRITER_LEASE_SECONDS
        )
        resp.raise_for_status()
        data = resp.json()
    if not data.get("candidates"):
        raise RuntimeError(f"no candidates: {str(data.get('error'))[:400]}")
    return data["candidates"]


def _opening_connect(text: str) -> bool:
    head = text[:OPENING_WINDOW]
    return any(tok in head for tok in VIEWER_TOKENS)


def measure(cands: list[str]) -> list[dict]:
    rows = []
    for c in cands:
        final = script_guard.ensure_closing(c)
        q = quality_gate.quality_review(final)
        f = q["features"]
        rows.append({
            "avg_slen": f["avg_slen"],
            "max_slen": f["max_slen"],
            "chars": f["chars"],
            "num_per_1k": f["num_per_1k"],
            "closing_ok": q["closing"]["ok"],
            "blocklist": len(q["blocklist"]),
            "publishable": script_guard.is_publishable(final),
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
          f"{'num/1k':>7} {'closing':>8} {'block':>6} {'pub':>5} {'open↔':>6}")
    for sd, r in zip(SEEDS, rows):
        print(f"  {sd:>5} {r['avg_slen']:>9} {r['max_slen']:>9} {r['chars']:>6} "
              f"{r['num_per_1k']:>7} {str(r['closing_ok']):>8} {r['blocklist']:>6} "
              f"{str(r['publishable']):>5} {str(r['open_connect']):>6}")
    print(f"  {'MEAN':>5} {_mean(rows, 'avg_slen'):>9} {_mean(rows, 'max_slen'):>9} "
          f"{_mean(rows, 'chars'):>6} {_mean(rows, 'num_per_1k'):>7}")


def _print_heads(name: str, rows: list[dict]) -> None:
    print(f"\n--- {name} 도입부(사람 검수용, B-3) ---")
    for sd, r in zip(SEEDS, rows):
        print(f"  [seed {sd}] {r['head']}")


def verdict(c_rows: list[dict], t_rows: list[dict]) -> None:
    c_avg, t_avg = _mean(c_rows, "avg_slen"), _mean(t_rows, "avg_slen")
    c_max, t_max = _mean(c_rows, "max_slen"), _mean(t_rows, "max_slen")
    c_num, t_num = _mean(c_rows, "num_per_1k"), _mean(t_rows, "num_per_1k")
    c_close, t_close = sum(r["closing_ok"] for r in c_rows), sum(r["closing_ok"] for r in t_rows)
    c_pub, t_pub = sum(r["publishable"] for r in c_rows), sum(r["publishable"] for r in t_rows)
    c_block, t_block = sum(r["blocklist"] for r in c_rows), sum(r["blocklist"] for r in t_rows)
    t_connect = sum(r["open_connect"] for r in t_rows)
    c_connect = sum(r["open_connect"] for r in c_rows)

    print("\n" + "=" * 64)
    print(f"control avg_slen={c_avg} max={c_max} num/1k={c_num} | "
          f"treatment avg_slen={t_avg} max={t_max} num/1k={t_num}")

    # B-1 회귀(필수)
    b1 = (
        t_avg <= B1_AVG_MAX
        and t_avg <= c_avg + B1_AVG_DRIFT
        and t_max <= c_max + B1_MAX_DRIFT
        and t_close >= c_close
        and t_pub >= c_pub
        and t_block <= c_block
        and t_num >= c_num - B1_NUM_DROP
    )
    # B-2 서사 프록시(보조)
    b2 = (t_connect >= c_connect) and (t_num >= c_num - B1_NUM_DROP)

    print(f"B-1 회귀(필수): {'PASS' if b1 else 'FAIL'} "
          f"(avg {c_avg}->{t_avg}≤{B1_AVG_MAX}, max {c_max}->{t_max}, "
          f"closing {c_close}->{t_close}, pub {c_pub}->{t_pub}, "
          f"block {c_block}->{t_block}, num {c_num}->{t_num})")
    print(f"B-2 서사프록시(보조): {'PASS' if b2 else 'FAIL'} "
          f"(open연결 {c_connect}->{t_connect}/{len(t_rows)}, num {c_num}->{t_num})")
    print("B-3 후킹/스토리(사람): 아래 도입부 샘플을 금지규칙 후킹 체크리스트로 직접 판정 — 자동 GO 아님")

    print("-" * 64)
    if not b1:
        print("판정: NO-GO(회귀) — 서사 fold가 2a/발행성 훼손. 문서만 착지(Gate A), fold 보류.")
    elif not b2:
        print("판정: 조건부 — 회귀는 없으나 서사 프록시 미개선. 문구 재설계 or fold 보류 검토.")
    else:
        print("판정: 자동 GREEN(B-1·B-2) — 단 B-3 사람검수 통과해야 최종 GO. 미통과 시 fold 보류.")
    print("=" * 64)


def main() -> None:
    settings = get_settings()
    redis = get_redis()
    control_p, treat_p = build_arms(TOPIC)
    print(f"TOPIC: {TOPIC} | SEEDS: {SEEDS} | writer: {settings.writer_url}")
    print("control 생성(현행 deployed)...")
    c_rows = measure(generate(settings, control_p, redis))
    print("treatment 생성(+A1 가이드보이스 +A2 구체성)...")
    t_rows = measure(generate(settings, treat_p, redis))
    _print_arm("control", c_rows)
    _print_arm("treatment", t_rows)
    _print_heads("treatment", t_rows)
    verdict(c_rows, t_rows)


if __name__ == "__main__":
    main()
