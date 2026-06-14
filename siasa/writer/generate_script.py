"""시사베테랑 대본 생성 엔트리포인트 — 작가 파이프라인 + 수치 검수 사이드카.

산출: <slug>.txt (seam 입력용 대본) + <slug>.review.txt (사람 팩트검수 체크리스트).
수치 게이트 = 모든 수치를 표면화(사람 검증/교체용). 모델 숫자는 신뢰 불가(주입 프로브로 확인).

실행: LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu ~/unsloth-venv/bin/python generate_script.py "주제" [출력경로]
"""
import os, sys, re
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unsloth import FastModel
import torch
from siasa_writer import SYSTEM, build_user_prompt, pick_best, GEN_CONFIG, EOS_ID
from numeric_gate import numeric_review
from quality_gate import quality_review, format_quality

_HERE = os.path.dirname(os.path.abspath(__file__))               # siasa/writer
BASE = os.environ.get("HERMES_DIR", os.path.dirname(_HERE))      # siasa/
LORA = os.environ.get("LORA", os.path.join(_HERE, "..", "adapters", "siasa_lora_e6"))
SEEDS = [11, 42, 77]


def format_review(report: dict) -> str:
    """수치 검수 체크리스트 텍스트(발행 전 사람이 모든 수치 검증)."""
    lines = ["=" * 60, "수치 검수 체크리스트 — 발행 전 모든 항목을 실제 데이터와 대조하세요",
             "(주의: 모델 숫자는 신뢰 불가. 표면화일 뿐 사실 검증 아님)", "=" * 60,
             f"총 수치 표현: {report['total_claims']}개\n"]
    for i, c in enumerate(report["claims"], 1):
        lines.append(f"[{i:2}] {c['value']}")
        lines.append(f"     ↳ {c['sentence']}")
    return "\n".join(lines)


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "원달러 환율이 천사백오십원을 넘었습니다"
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_HERE, "..", "samples", "대본.txt")

    model, tok = FastModel.from_pretrained(LORA, max_seq_length=8192, load_in_4bit=True)
    FastModel.for_inference(model)
    tk = getattr(tok, "tokenizer", tok)
    user = build_user_prompt(topic, 4500)
    prompt = tok.apply_chat_template(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        tokenize=False, add_generation_prompt=True)

    cands = []
    for sd in SEEDS:
        torch.manual_seed(sd)
        inp = tk(prompt, return_tensors="pt").to("cuda")
        n = inp["input_ids"].shape[1]
        o = model.generate(**inp, max_new_tokens=5200, do_sample=True, eos_token_id=EOS_ID,
                           pad_token_id=tk.pad_token_id, **GEN_CONFIG)
        cands.append(tk.decode(o[0][n:], skip_special_tokens=True).strip())

    final, structural_ok = pick_best(cands)
    review = numeric_review(final)
    quality = quality_review(final)              # 현행 39편 대비 스타일 A/B(사람 go/no-go)

    open(out, "w", encoding="utf-8").write(final)
    rev_path = re.sub(r"\.txt$", "", out) + ".review.txt"
    open(rev_path, "w", encoding="utf-8").write(
        format_review(review) + "\n\n" + format_quality(quality))

    print(f"대본: {out} ({len(final)}자, 구조게이트={'통과' if structural_ok else '미달'})")
    print(f"검수리스트: {rev_path} (수치 {review['total_claims']}개 — 발행 전 사람 검증 필수)")
    print(f"품질게이트: verdict={quality['verdict']} "
          f"편차 {len(quality['flags'])}개 · 신뢰도저하 {len(quality['blocklist'])}개")


if __name__ == "__main__":
    main()
