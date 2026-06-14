#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시사베테랑 작가 프로필 → ASB gateway /v1/writer 클라이언트 (순수 stdlib).

writer 프로필은 in-context로 대본을 직접 쓰지 않고, 이 헬퍼로 GPU writer
파이프라인(gemma4 + 시사베테랑 LoRA · 아웃라인 스캐폴딩 · best-of-N · 구조 가드
· 수치 게이트)에 위임한다.

산출:
  <out>.txt          seam 입력 대본 (split_scenes.py 입력)
  <out>.review.txt   발행 전 사람 수치 검수 체크리스트

수치는 모델이 신뢰 불가(주입 프로브로 확정) → 검수리스트로 전수검증 후 발행.

환경변수:
  ASB_GATEWAY_URL  게이트웨이 베이스 URL (기본 http://gateway:8000)
  ASB_API_KEY      게이트웨이 Bearer 키 (필수)
  SIASA_OUT_DIR    기본 출력 디렉터리 (out 인자 미지정 시)

실행:
  python3 call_writer.py "<주제>" [출력경로] [--seeds 11,42] \
      [--min-chars 4500] [--max-new-tokens 5200]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://gateway:8000"
# 게이트웨이는 upstream writer 호출 동안 GPU 락(WRITER_LEASE 3900s)을 보유할 수 있다.
# best-of-N 생성 + 락 대기까지 흡수하도록 넉넉히 잡는다(짧은 타임아웃 = 거짓 실패).
TIMEOUT_SECONDS = 4000


def format_review(report: dict) -> str:
    """수치 검수 체크리스트 텍스트(generate_script.py와 동일 포맷).

    발행 전 사람이 모든 수치를 실제 데이터와 대조/교체한다.
    """
    lines = [
        "=" * 60,
        "수치 검수 체크리스트 — 발행 전 모든 항목을 실제 데이터와 대조하세요",
        "(주의: 모델 숫자는 신뢰 불가. 표면화일 뿐 사실 검증 아님)",
        "=" * 60,
        f"총 수치 표현: {report.get('total_claims', 0)}개\n",
    ]
    for i, claim in enumerate(report.get("claims", []), 1):
        lines.append(f"[{i:2}] {claim.get('value', '')}")
        lines.append(f"     ↳ {claim.get('sentence', '')}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="ASB /v1/writer 대본 생성 클라이언트")
    ap.add_argument("topic", help="대본 주제")
    ap.add_argument(
        "out",
        nargs="?",
        default=os.path.join(os.environ.get("SIASA_OUT_DIR", "."), "대본.txt"),
        help="출력 대본 경로 (기본: $SIASA_OUT_DIR/대본.txt)",
    )
    ap.add_argument("--seeds", default="11,42", help="best-of-N 시드 (쉼표구분, 기본 11,42)")
    ap.add_argument("--min-chars", type=int, default=4500)
    ap.add_argument("--max-new-tokens", type=int, default=5200)
    return ap.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    base = os.environ.get("ASB_GATEWAY_URL", DEFAULT_URL).rstrip("/")
    api_key = os.environ.get("ASB_API_KEY", "")
    if not api_key:
        print("ERROR: ASB_API_KEY 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        return 2

    try:
        seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    except ValueError:
        print(f"ERROR: --seeds 파싱 실패: {args.seeds!r}", file=sys.stderr)
        return 2
    if not seeds:
        print("ERROR: --seeds 가 비었습니다.", file=sys.stderr)
        return 2

    payload = json.dumps(
        {
            "topic": args.topic,
            "seeds": seeds,
            "min_chars": args.min_chars,
            "max_new_tokens": args.max_new_tokens,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/v1/writer",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        print(f"ERROR: gateway HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"ERROR: gateway 연결/타임아웃 실패: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: 응답 JSON 파싱 실패: {exc}", file=sys.stderr)
        return 1

    script = data.get("script", "")
    if not script:
        print(f"ERROR: 빈 대본 응답: {json.dumps(data, ensure_ascii=False)[:500]}", file=sys.stderr)
        return 1

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(script)

    review = data.get("numeric_review", {})
    review_path = re.sub(r"\.txt$", "", out_path) + ".review.txt"
    with open(review_path, "w", encoding="utf-8") as fh:
        fh.write(format_review(review))

    structural_ok = data.get("structural_ok")
    print(f"대본: {out_path} ({len(script)}자, 구조게이트={'통과' if structural_ok else '미달'})")
    print(
        f"검수리스트: {review_path} "
        f"(수치 {review.get('total_claims', 0)}개 — 발행 전 사람 검증 필수)"
    )
    print(f"id={data.get('id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
