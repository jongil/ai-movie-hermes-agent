"""영상팀 핸드오프 — Hermes 산출 대본.txt를 영상 파이프라인 입력 위치에 배치.

영상 파이프라인(`ai-movie-generator/all_in_one_start.sh <date>`)은 `$WORK_DIR/<date>/대본.txt`를
읽는다. 형태는 코퍼스 대본.txt와 동일(헤더無·클로징·아라비아0) → **순수 복사**.

설계: .work_dir 권위 출처(하드코딩 안 함) · refuse-if-exists(실제 발행 코퍼스 클로버 방지) ·
자동 트리거 안 함(파일 배치 + 안내만). **Mac-side 실행**(영상 파이프·~/docs는 로컬, Hermes 번들은 마운트).

실행: python3 handoff_to_video.py --script <대본.txt> --date YYYY-MM-DD [--work-dir DIR] [--force]
"""
from __future__ import annotations

import argparse
import shutil
import unicodedata
from pathlib import Path

# repo 레이아웃: .../ai-movie-project/{ai-movie-hermes-agent/siasa/orchestrator/, ai-movie-generator/}
_DEFAULT_GENERATOR = Path(__file__).resolve().parents[3] / "ai-movie-generator"
SCRIPT_NAME = unicodedata.normalize("NFC", "대본.txt")   # 파이프라인이 읽는 고정 파일명(NFC)


def resolve_work_dir(generator_repo: str | Path = _DEFAULT_GENERATOR) -> str:
    """영상 파이프라인의 권위 출처 `.work_dir`에서 작업 디렉터리를 읽는다."""
    wf = Path(generator_repo) / ".work_dir"
    if not wf.exists():
        raise ValueError(f".work_dir 없음: {wf} — 영상 파이프라인 repo 경로(--work-dir) 확인.")
    return unicodedata.normalize("NFC", wf.read_text(encoding="utf-8").strip())


def handoff(script_path: str, date: str, work_dir: str, force: bool = False) -> str:
    """대본.txt를 `<work_dir>/<date>/대본.txt`로 복사(refuse-if-exists). dest 반환."""
    src = Path(script_path)
    if not src.exists():
        raise FileNotFoundError(f"대본 없음: {src}")
    dest = Path(work_dir) / date / SCRIPT_NAME
    if dest.exists() and not force:
        raise FileExistsError(f"이미 존재(실제 코퍼스일 수 있음): {dest} — 덮어쓰려면 --force.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)               # 순수 복사(transform 없음)
    return str(dest)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="영상팀 핸드오프(대본.txt 배치)")
    ap.add_argument("--script", required=True, help="Hermes 산출 대본.txt 경로")
    ap.add_argument("--date", required=True, help="대상 날짜 YYYY-MM-DD (= all_in_one_start.sh 인자)")
    ap.add_argument("--work-dir", default=None, help="영상 work_dir(기본: ai-movie-generator/.work_dir)")
    ap.add_argument("--force", action="store_true", help="기존 대본.txt 덮어쓰기(주의: 코퍼스)")
    return ap.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    wd = args.work_dir or resolve_work_dir()
    dest = handoff(args.script, args.date, wd, force=args.force)
    print(f"핸드오프 완료: {dest}")
    print(f"다음: cd ai-movie-generator && ./all_in_one_start.sh {args.date}")
