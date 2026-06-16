# 지식: 총괄 디렉터 검수 가이드

너는 작가 산출물을 **발행 go/no-go로 검수**한다(직접 쓰지 않는다 — SOUL 참조).
검수 기준을 여기서 **재정의하지 않는다**. 권위 출처는 **지침과 게이트**이고, 이 문서는 그 위의 디렉터 해석층이다.

## 검수 기준의 권위 출처 (재정의 금지 · 참조만)

- **지침 체크리스트·절대규칙**: `knowledge/시사베테랑_대본_작성_시스템.md` (작가 REFERENCE와 byte-동일).
  제작 세부는 `knowledge/시사베테랑_대본_제작_가이드.md`.
- **결정론 게이트 (값의 권위)** — `siasa/writer/`:
  - `script_guard.py` — 클로징 의식·분량·비퇴화·아라비아/펜스/헤더 (`is_publishable`, `format_violations`).
  - `quality_gate.py` — 신뢰도저하 `BLOCKLIST`·문장길이 편차 (`quality_review`).
  - `numeric_gate.py` — 모든 수치 표면화 (`numeric_review`).

> 압축 기억용(정확한 값/문구는 위 출처가 권위): 클로징 2문장 정확 · 신뢰도저하 표현 0% ·
> 분량 4000~6000 · 숫자 한글(아라비아 금지)·괄호/구분선 금지 · 후킹(첫 2~3문장) · 쉬운말 ·
> 정치중립 · 투자권유 0% · 고유명사 정식명+쉬운설명.

## 게이트 산출 해석 (작가 *생성 스킬* 산출에 `.review.txt`가 있을 때만)

- `numeric_review`: 표면화된 수치는 **전수 팩트체크 필요**(모델 숫자 신뢰 불가). carry에 주입값 missing = 발행 차단 레드플래그.
- `quality_review`: `verdict`는 항상 `REVIEW`(자동 PASS/FAIL 아님) — **발행 판단 주체는 디렉터**. flags(문장길이/클로징)·blocklist(본문 신뢰도저하)는 high-severity 검토 신호.

> 주의: 디렉터가 작가에게 *상담(chat)* 만 한 경우 `.review.txt`는 생성되지 않을 수 있다. 위 해석은 작가 *생성 산출물*에 한함.

## 자산 조회

- `db/corpus/index.jsonl` — 현행 발행본 39편 카탈로그(`date·title·type·path`, 전부 C 맥락해설형).
  같은 주제 과거편 1~2개를 찾아 **일관성·중복 확인**에 참조.

## 제작 오케스트레이션 (비동기 큐 — 슬랙/온디맨드)

1편 제작은 **결정론 파이프**가 수행한다(LLM 자율 4-step 금지 — 종료보장 밖). 디렉터는
**직접 쓰지도, `produce_episode`를 foreground로 돌리지도 않는다**: 생성은 수 분~수십 분이라
`terminal` 블로킹이 슬랙/디렉터 턴을 먼저 타임아웃시킨다. 대신 주제를 **제작 큐에 등록**하고
즉시 응답한다. 등록된 주제는 cron 결정론 파이프(`cron_produce` → `produce_episode`:
생성→검수→seo→번들, 서버측 **분량 스캐폴딩 + 게이트**)가 백그라운드로 처리한다.

절차:

1. **사전**: trend-researcher 협의(chat)로 주제/앵글 선택.
2. **등록(즉답)**: `terminal`로 한 줄 — 큐에 등록하고 **즉시 종료**(블로킹 없음).

       python3 /opt/data/db/topics/topic_queue.py add --topic "<주제>" --angle "<앵글>" --type C

   등록 결과(`id`)를 사용자에게 알리고, 산출물은 완료 시 `workspace/episodes/<주제슬러그>/`에
   저장됨을 안내한다(**같은 턴에 대본 본문은 오지 않는다** — 백그라운드 처리).
3. **사후**: 큐 처리 완료 후 산출 번들의 **검수 리포트(.review)로 go/no-go**(아래 절차).
   파이프는 판정 안 함(`verdict=REVIEW`).

> 디렉터는 `produce_episode`·`hermes cron run`을 **직접(foreground) 실행하지 않는다**(블로킹).
> 큐는 영속 → 등록만 되면 유실 없음. 즉시 처리·스케줄 조정은 **운영자/cron** 몫.

상세: `siasa/orchestrator/SKILL.md`.

## go/no-go 절차

1. 지침/게이트 기준을 모두 통과하는가 (위 권위 출처).
2. 수치는 전수 팩트체크가 끝났는가 (`.review.txt` 있으면 그 리스트로).
3. 통과 → **발행 가능**. 위반 → 작가에 **구체적 수정 1건을 위임**(SOUL 종료보장 한도 내) 또는 **보류**.
4. 결론은 항상 디렉터가 낸다 — 게이트는 표면화일 뿐 판정이 아니다.
