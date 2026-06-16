"""디렉터 E2E 제작 파이프 — 결정론 오케스트레이션(종료보장=스크립트 exit).

단계: 대본 생성(call_writer 직접) → 검수(.review.txt) → seo 카피(seo-director chat) → 번들.
LLM 디렉터 역할은 ①trend 협의로 앵글 선택(사전) ②검수 리포트로 최종 go/no-go(사후). 본 스크립트는
판정하지 않는다(verdict=REVIEW) — 게이트는 표면화일 뿐.

생성·seo runner는 주입 가능(테스트 stub). 실행 runner는 thin subprocess 래퍼.
실행: python3 produce_episode.py --topic "..." [--workspace DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

HERMES_HOME = os.environ.get("HERMES_DIR", "/opt/data")
CALL_WRITER = f"{HERMES_HOME}/profiles/writer/skills/siasa-writer/call_writer.py"
WRITER_ENV = f"{HERMES_HOME}/profiles/writer/.env"
HERMES_BIN = os.environ.get("HERMES_BIN", "/opt/hermes/.venv/bin/hermes")
GEN_TIMEOUT = 4200   # 대본 생성(GPU LoRA, WRITER_LEASE 흡수)
SEO_TIMEOUT = 600


def _gen_via_call_writer(topic: str, out_path: str) -> None:
    """call_writer.py 직접 실행(결정론). writer .env(ASB_API_KEY) source. injection-safe 인자전달."""
    script = 'set -a; . "$1" 2>/dev/null; set +a; exec python3 "$2" "$3" "$4"'
    subprocess.run(["bash", "-c", script, "_", WRITER_ENV, CALL_WRITER, topic, out_path],
                   check=True, timeout=GEN_TIMEOUT)


def _seo_via_chat(script_text: str) -> str:
    """seo-director에 chat 협의(검증된 leaf 호출)로 SEO 자산 요청."""
    prompt = ("다음 대본의 SEO 자산(제목 후보·설명·태그·썸네일 카피)을 만들어줘:\n\n"
              + script_text[:3000])
    out = subprocess.run([HERMES_BIN, "-p", "seo-director", "chat", "-q", prompt],
                         capture_output=True, text=True, timeout=SEO_TIMEOUT)
    return out.stdout.strip()


def produce_episode(
    topic: str,
    workspace: str,
    gen_runner: Callable[[str, str], None] | None = None,
    seo_runner: Callable[[str], str] | None = None,
) -> dict:
    """1편 제작 번들 + 검수 리포트 산출. 결정론 시퀀스, 반환=구조적 종료."""
    gen_runner = gen_runner or _gen_via_call_writer
    seo_runner = seo_runner or _seo_via_chat

    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    script_path = ws / "대본.txt"
    review_path = ws / "대본.review.txt"

    gen_runner(topic, str(script_path))                       # 1. 생성(핀 경로)
    if not script_path.exists():
        raise RuntimeError(f"생성 실패: {script_path} 없음")
    script = script_path.read_text(encoding="utf-8")
    review = review_path.read_text(encoding="utf-8") if review_path.exists() else ""  # 2. 검수

    seo = seo_runner(script)                                   # 3. seo 카피(생성 대본 기반)

    bundle = {                                                 # 4. 번들
        "topic": topic,
        "script_path": str(script_path),
        "review_path": str(review_path),
        "script_chars": len(script),
        "seo": seo,
    }
    (ws / "seo.txt").write_text(seo, encoding="utf-8")
    (ws / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "verdict": "REVIEW",                                  # 자동 판정 아님 — 디렉터가 go/no-go
        "bundle_path": str(ws / "bundle.json"),
        "script_chars": len(script),
        "review": review,
        "seo": seo,
    }


def _default_workspace(topic: str) -> str:
    base = os.environ.get("SIASA_OUT_DIR") or f"{HERMES_HOME}/workspace/episodes"
    slug = "".join(c if c.isalnum() else "_" for c in topic)[:40] or "episode"
    return str(Path(base) / slug)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="디렉터 E2E 제작 파이프")
    ap.add_argument("--topic", required=True, help="대본 주제(앵글 포함 권장)")
    ap.add_argument("--workspace", default=None, help="출력 워크스페이스(기본 $SIASA_OUT_DIR/슬러그)")
    return ap.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    ws = args.workspace or _default_workspace(args.topic)
    rep = produce_episode(args.topic, ws)
    print(f"\n=== 제작 번들: {rep['bundle_path']} ===")
    print(f"대본 {rep['script_chars']}자 · verdict={rep['verdict']}(디렉터 go/no-go 필요)")
    print(f"\n--- 검수 리포트(.review) ---\n{rep['review'][:2000]}")
    print(f"\n--- SEO 카피 ---\n{rep['seo'][:1500]}")
    sys.exit(0)
