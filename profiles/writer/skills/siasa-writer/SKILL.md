---
name: siasa-writer
description: "주제를 받아 ASB GPU 작가 파이프라인(/v1/writer)에 위임해 시사베테랑 대본을 생성한다. in-context 작성 금지 — 항상 이 스킬로 위임."
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [siasa, writer, script, asb, gateway]
    related_skills: []
---

# 시사베테랑 대본 생성 (ASB /v1/writer 위임)

## 개요

시사베테랑 대본은 **이 스킬로만 생성**한다. 대본 본문을 in-context로 직접 쓰지 않는다.
실제 생성은 ASB 게이트웨이 `/v1/writer`가 GPU 작가 서비스(gemma4 + 시사베테랑 LoRA)에
위임하며, 서버측에서 아웃라인 스캐폴딩 · best-of-N · 구조 가드 · 수치 게이트를 수행한다.

작성 규칙(타입 A/B/C 구조 · 후킹 · 쉬운말 · 고유명사 · 금지표현 · 클로징)은 이미
파이프라인과 LoRA에 내장되어 있다. 원문 지침은 프로필의 `REFERENCE_writing_system.md` 참고.

## 사전 요건

- `bash` / `python3` 사용 가능 (헬퍼는 순수 stdlib, torch 불요).
- 프로필 `.env`에 다음이 설정되어 있어야 한다:
  - `ASB_GATEWAY_URL` (기본 `http://gateway:8000`)
  - `ASB_API_KEY` (게이트웨이 Bearer 키)
- 컨테이너가 `ai-source-builder_asb` 네트워크에 합류해 `gateway`를 resolve 할 수 있어야 한다.

## 입력

1. **주제** — 한 줄 주제 또는 첨부 자료 요약.
2. (선택) **출력 경로** — 기본 `$SIASA_OUT_DIR/대본.txt` (미설정 시 현재 디렉터리).

## 절차

> 모든 bash 호출은 **반드시 프로필 `.env`를 먼저 source** 한다(`ASB_GATEWAY_URL`·`ASB_API_KEY`
> 주입). Hermes 자동주입에 의존하지 않고 스킬이 자기완결적으로 로드한다.

1. **(선택) 헬스/네트워크 확인** — 첫 사용 시에만:
   ```bash
   set -a; . /opt/data/profiles/writer/.env; set +a
   curl -fsS "$ASB_GATEWAY_URL/healthz" && echo OK
   ```

2. **대본 생성 위임** — 헬퍼를 1회 실행한다(생성은 GPU 락 직렬화로 수 분 소요).
   경로는 컨테이너 절대경로(HERMES_HOME=`/opt/data`)를 쓴다:
   ```bash
   set -a; . /opt/data/profiles/writer/.env; set +a
   python3 /opt/data/profiles/writer/skills/siasa-writer/call_writer.py \
     "<주제>" "<출력경로>"
   # 예: 파이프라인 경합 시 단일 시드로 빠르게(--seeds 11)
   ```
   산출:
   - `<출력경로>` — seam 입력 대본 (`split_scenes.py` 입력 규약 준수).
   - `<출력경로 .txt 제거>.review.txt` — 수치 검수 체크리스트.

3. **수치 검수 안내 (필수)** — 생성된 대본의 숫자는 **신뢰 불가**(모델 한계, 진단 확정).
   `.review.txt`의 모든 수치를 실제 데이터와 대조/교체하기 전에는 **발행 불가**임을 명시한다.

4. **보고** — 분량(자), 구조게이트 통과 여부, 수치 항목 수, 대본 파일 경로를 요약 보고한다.

## 주의

- ❌ 대본 본문을 직접 작성하지 않는다(위임 전용).
- ❌ 수치 미검수 대본을 "발행 가능"으로 보고하지 않는다.
- ✅ 호출은 1회 — 응답이 수 분 걸려도 재시도/중복 호출하지 않는다(헬퍼 타임아웃 4000초).
- 게이트웨이 5xx/타임아웃 시 헬퍼가 비정상 종료코드를 반환한다 → 보고 후 사용자 판단.
