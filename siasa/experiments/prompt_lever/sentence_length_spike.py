#!/usr/bin/env python3
"""프롬프트 레버 스파이크 — 문장길이 지침이 avg_slen을 움직이는가 (LoRA-vs-prompt 판정).

크럭스: SYSTEM/프롬프트 변경이 LoRA 출력을 실제로 움직이는가? (v2/v3 "LoRA가 in-context 압도").
control(현행 SYSTEM/user) vs treatment(+문장길이 지침)을 동일 시드셋으로 생성, quality_gate
전체 리포트로 비교한다. 재배포 0 — writer 서비스 /generate 레이어에서 system/user만 오버라이드.

실행(서버, gateway 컨테이너 내):
  docker cp .../sentence_length_spike.py <gateway_container>:/tmp/spike.py
  docker exec <gateway_container> python /tmp/spike.py

GPU 안전: 직접 /generate는 게이트웨이 락을 우회 → 16GB 공유 OOM 위험. 각 팔을 gpu_lock으로
직렬화(ComfyUI/Ollama와 배타). 사전등록 3게이트로 판정.
"""
from __future__ import annotations

import statistics as st
import sys

# 컨테이너 내 경로: gateway 패키지(/app) + 순수파이썬 siasa 사본(/app/gateway/siasa)
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/gateway/siasa")

import httpx  # noqa: E402

import quality_gate  # noqa: E402
import script_guard  # noqa: E402
import siasa_writer  # noqa: E402
from gateway.config import get_settings  # noqa: E402
from gateway.queue.connection import get_redis  # noqa: E402
from gateway.queue.gpu_lock import WRITER_LEASE_SECONDS, gpu_lock  # noqa: E402

# 실측 결함(avg_slen 44.7)을 낸 production 에피소드와 동일 주제 계열 → Gate 0(결함 재현) 충족 목적
TOPIC = "인공지능 규제와 일자리 충격"
SEEDS = [11, 42, 7]  # 양 팔 동일 시드셋 ≥3 (시드노이즈 분리)
MAX_NEW = 5200

# 격리된 단일 레버: 문장길이 지침만 추가(수치 요구 완화는 번들 금지 — 별도 트랙)
SLEN_INSTRUCTION = (
    "문장은 짧고 단정하게 끊어 쓰세요. 한 문장은 한 호흡(약 마흔 자 이내)에 읽히도록 하고, "
    "긴 문장은 두세 문장으로 나누세요."
)

# 사전등록 게이트
GATE0_REPRO_MIN = 40.0   # control mean avg_slen이 이보다 높아야 결함 재현(베이스 ~32 << 관측 44.7)
GATE1_GO_MAX = 37.0      # treatment mean avg_slen ≤ 37 (베이스 mean ~32)


def build_arms(topic: str) -> tuple[dict[str, str], dict[str, str]]:
    base_sys = siasa_writer.SYSTEM
    base_user = siasa_writer.build_user_prompt(topic)
    control = {"system": base_sys, "user": base_user}
    treatment = {
        "system": base_sys + " " + SLEN_INSTRUCTION,
        "user": base_user + SLEN_INSTRUCTION + "\n",
    }
    return control, treatment


def generate(settings, prompt: dict[str, str], redis) -> list[str]:
    """gpu_lock 하에 한 팔 생성(1 /generate = 1 모델로드, N시드)."""
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


def measure(cands: list[str]) -> list[dict]:
    """발행 형태(ensure_closing 적용)로 전체 quality_review 측정 — 부수피해 감지(Gate 2)."""
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
        })
    return rows


def _mean(rows: list[dict], k: str) -> float:
    vals = [r[k] for r in rows]
    return round(st.mean(vals), 1) if vals else 0.0


def _print_arm(name: str, rows: list[dict]) -> None:
    print(f"\n[{name}] n={len(rows)}")
    print(f"  {'seed':>5} {'avg_slen':>9} {'max_slen':>9} {'chars':>6} "
          f"{'num/1k':>7} {'closing':>8} {'block':>6} {'pub':>5}")
    for sd, r in zip(SEEDS, rows):
        print(f"  {sd:>5} {r['avg_slen']:>9} {r['max_slen']:>9} {r['chars']:>6} "
              f"{r['num_per_1k']:>7} {str(r['closing_ok']):>8} {r['blocklist']:>6} "
              f"{str(r['publishable']):>5}")
    print(f"  {'MEAN':>5} {_mean(rows, 'avg_slen'):>9} {_mean(rows, 'max_slen'):>9} "
          f"{_mean(rows, 'chars'):>6} {_mean(rows, 'num_per_1k'):>7}")


def verdict(c_rows: list[dict], t_rows: list[dict]) -> None:
    c_avg = _mean(c_rows, "avg_slen")
    t_avg = _mean(t_rows, "avg_slen")
    print("\n" + "=" * 60)
    print(f"control mean avg_slen = {c_avg} | treatment mean avg_slen = {t_avg}")

    gate0 = c_avg >= GATE0_REPRO_MIN
    gate1 = (t_avg <= GATE1_GO_MAX) and (t_avg < c_avg)
    # Gate 2: 부수피해 — closing/publishable이 control 대비 나빠지지 않을 것
    c_close = sum(r["closing_ok"] for r in c_rows)
    t_close = sum(r["closing_ok"] for r in t_rows)
    c_pub = sum(r["publishable"] for r in c_rows)
    t_pub = sum(r["publishable"] for r in t_rows)
    c_num = _mean(c_rows, "num_per_1k")
    t_num = _mean(t_rows, "num_per_1k")
    gate2 = (t_close >= c_close) and (t_pub >= c_pub) and (t_num >= c_num - 1.5)

    print(f"Gate 0 (결함재현 control≥{GATE0_REPRO_MIN}): {'PASS' if gate0 else 'FAIL'} ({c_avg})")
    print(f"Gate 1 (GO treat≤{GATE1_GO_MAX} & <control): {'PASS' if gate1 else 'FAIL'} ({t_avg})")
    print(f"Gate 2 (부수피해 없음): {'PASS' if gate2 else 'FAIL'} "
          f"(closing {c_close}->{t_close}, pub {c_pub}->{t_pub}, num/1k {c_num}->{t_num})")

    print("-" * 60)
    if not gate0:
        print("판정: INCONCLUSIVE — control이 결함 미재현. 주제/시드 재검토 후 재실행.")
    elif gate1 and gate2:
        print("판정: GO — 프롬프트 레버 작동. Phase 2(ebook 증류→SYSTEM/OUTLINE) 진행.")
    elif gate1 and not gate2:
        print("판정: 조건부 — avg_slen은 내려가나 부수피해 발생. 지침 약화/재설계 필요.")
    else:
        print("판정: NO-GO — 문장길이가 LoRA-baked. Phase 2 보류, 재학습 트랙 검토.")
    print("=" * 60)


def main() -> None:
    settings = get_settings()
    redis = get_redis()
    control_p, treat_p = build_arms(TOPIC)
    print(f"TOPIC: {TOPIC} | SEEDS: {SEEDS} | writer: {settings.writer_url}")
    print("control 생성(현행)...")
    c_rows = measure(generate(settings, control_p, redis))
    print("treatment 생성(+문장길이 지침)...")
    t_rows = measure(generate(settings, treat_p, redis))
    _print_arm("control", c_rows)
    _print_arm("treatment", t_rows)
    verdict(c_rows, t_rows)


if __name__ == "__main__":
    main()
