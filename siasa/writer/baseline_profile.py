"""현행 발행본 39편 스타일 분포 → baseline_profile.json 동결(품질 게이트 A/B 기준).

베이스라인 = is_publishable 통과편(현행 컨벤션 2026-04-13~). 구포맷 자동 제외.
재현: python3 baseline_profile.py [코퍼스_glob]
"""
from __future__ import annotations
import glob
import json
import statistics as st
import sys
from pathlib import Path

from quality_gate import extract_style_features
from script_guard import is_publishable

DEFAULT_GLOB = "/Users/gdash/docs/경제베테랑-youtube/2026-*/대본.txt"
PROFILE_FEATURES = ("chars", "n_sent", "avg_slen", "max_slen", "n_para", "n_num", "num_per_1k")


def _pct(sorted_vals: list[float], q: float) -> float:
    """선형보간 분위수(외부 의존 없이)."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx)
    frac = idx - lo
    hi = min(lo + 1, len(sorted_vals) - 1)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac, 2)


def build_profile(corpus_glob: str = DEFAULT_GLOB) -> dict:
    files = [f for f in sorted(glob.glob(corpus_glob))
             if is_publishable(Path(f).read_text(encoding="utf-8"))]
    feats = [extract_style_features(Path(f).read_text(encoding="utf-8")) for f in files]
    out: dict = {"n_samples": len(files), "features": {}}
    for key in PROFILE_FEATURES:
        vals = sorted(f[key] for f in feats)
        out["features"][key] = {
            "mean": round(st.mean(vals), 2),
            "std": round(st.pstdev(vals), 2) if len(vals) > 1 else 0.0,
            "p10": _pct(vals, 0.10),
            "p90": _pct(vals, 0.90),
            "min": vals[0],
            "max": vals[-1],
        }
    return out


if __name__ == "__main__":
    g = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GLOB
    profile = build_profile(g)
    dest = Path(__file__).with_name("baseline_profile.json")
    dest.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"baseline_profile.json 동결: n={profile['n_samples']}")
    for k, b in profile["features"].items():
        print(f"  {k:<12} mean={b['mean']:<9} p10={b['p10']:<8} p90={b['p90']:<8} [{b['min']}, {b['max']}]")
