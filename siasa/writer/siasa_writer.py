"""시사베테랑 작가 — e6 LoRA + 아웃라인 스캐폴딩 + 가드(best-of-N).

분량 레버 = 구체 소제목 아웃라인(naive ~2.3K → ~3.3-3.5K). 이어쓰기/재작성은
LoRA의 완결 아크 학습 때문에 ~2.5K 천장에 막혀 채택 안 함.
형식·클로징은 가드(ensure_closing)가 결정론 보장.
"""
from __future__ import annotations
import re

CLOSE = "복잡한 세상, 제대로 읽어갑시다"
SYSTEM = (
    "당신은 시사 베테랑 채널의 임한수 작가입니다. 주어진 주제로 5070 시니어 대상 시사·경제 "
    "유튜브 내레이션 대본을 작성합니다. 팩트 기반 분석, 후킹 도입, 쉬운 말 변환, 한글 숫자 표기, "
    "마지막 채널 멘트를 지킵니다."
)
# 시사베테랑 가이드 구조 → 채울 섹션을 명시해 단일패스 분량 확보
OUTLINE = [
    "충격적 사실이나 질문으로 시작하는 후킹 도입",
    "이 사안의 큰 그림과 배경",
    "첫 번째 핵심 원인 자세히",
    "두 번째 핵심 원인 자세히",
    "세 번째 핵심 원인 자세히",
    "우리 생활 물가에 미치는 영향",
    "기업과 일자리에 미치는 영향",
    "금융시장과 개인 자산에 미치는 영향",
    "정부나 당국의 대응과 그 한계",
    "비슷한 과거 사례나 해외 비교",
    "앞으로의 전망 시나리오",
    "시청자가 준비할 첫 번째 대비책",
    "시청자가 준비할 두 번째 대비책",
    "시청자가 준비할 세 번째 대비책",
    "마무리 인사와 클로징 두 문장",
]
GEN_CONFIG = dict(repetition_penalty=1.3, no_repeat_ngram_size=8, temperature=0.7, top_p=0.9)
EOS_ID = 106  # gemma4 <turn|>


def build_user_prompt(topic: str, min_chars: int = 4500) -> str:
    """아웃라인 스캐폴딩 user 프롬프트 — 채울 섹션을 명시해 분량 유도."""
    flow = "\n".join(f"{i+1}) {s}" for i, s in enumerate(OUTLINE))
    return (
        f"주제: {topic}\n\n"
        f"이 주제로 시사베테랑 대본을 작성하되, 아래 흐름을 모두 충분히 길고 깊게 풀어 "
        f"전체 본문이 {_kor_num(min_chars)} 이상이 되게 작성해 주세요. "
        "각 단락마다 구체적 수치(한글로), 사례, 일상 비유를 넣고 절대 요약하지 마세요.\n" + flow + "\n"
    )


def _kor_num(n: int) -> str:
    return {3000: "삼천자", 3500: "삼천오백자", 4000: "사천자", 4500: "사천오백자", 5000: "오천자"}.get(n, f"{n}자")


def pick_best(candidates: list[str]):
    """가드 적용 후 best 선택: 발행가능 중 최장, 없으면 비퇴화 최장.

    siasa_writer는 script_guard에 의존하지만 순환참조 방지 위해 지연 import.
    """
    from script_guard import ensure_closing, is_publishable, detect_degenerate
    finals = [ensure_closing(c) for c in candidates]
    pub = [t for t in finals if is_publishable(t)]
    if pub:
        return max(pub, key=len), True
    nondeg = [t for t in finals if not detect_degenerate(t)] or finals
    return max(nondeg, key=len), False
