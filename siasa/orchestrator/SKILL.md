# 제작 오케스트레이션 (produce_episode)

디렉터가 **종료보장 하에** 1편 제작을 오케스트레이션하는 **결정론 스크립트**.
LLM 자율 4-step이 아니라 코드 시퀀스 → 스크립트 exit = 구조적 종료보장.

## 무엇을 하나

1. **대본 생성** — `call_writer.py` 직접 호출(결정론) → `대본.txt` + `대본.review.txt`(핀 워크스페이스)
2. **검수** — `.review.txt`(수치+품질 게이트) 읽어 리포트
3. **seo 카피** — `seo-director` chat 협의 → 제목·설명·태그·썸네일
4. **번들** — `bundle.json` + `seo.txt`. `verdict=REVIEW`(자동 판정 아님)

## 디렉터 역할 (LLM)

- **사전**: trend-researcher 협의로 주제/앵글 선택(검증된 chat).
- **실행**: 아래 한 줄로 결정론 파이프 실행.
- **사후**: 출력 **검수 리포트로 최종 go/no-go** 판단(스크립트는 판정 안 함).

## 실행

```bash
python3 /opt/data/siasa/orchestrator/produce_episode.py --topic "<앵글 포함 주제>" [--workspace DIR]
```

- writer `.env`(ASB_API_KEY)는 스크립트가 자동 source. 디렉터로 키 복제 불요.
- 워크스페이스 미지정 시 `$SIASA_OUT_DIR/<슬러그>`.
- 생성은 GPU LoRA라 수 분 소요(WRITER_LEASE 흡수).

## cron 자율 제작 (--no-agent, 결정론)

주제 큐(`db/topics/queue.jsonl`)에서 pop해 자동 제작. **LLM 자율 없음** — `cron_produce.py`가
tick당 1편(lock으로 overrun 차단), 성공→`done`+번들 stdout / 실패→`error`.

**배포** (shim은 `~/.hermes/scripts/` 필수 = ephemeral → 컨테이너 재생성 시 재배포):

```bash
# 1) shim 생성(~/.hermes/scripts/ 상대 파일명만 허용 — repo 스크립트를 exec)
mkdir -p ~/.hermes/scripts
printf '#!/usr/bin/env bash\nexec python3 /opt/data/siasa/orchestrator/cron_produce.py\n' \
  > ~/.hermes/scripts/produce_cron.sh
chmod +x ~/.hermes/scripts/produce_cron.sh
# 2) cron 등록(정의는 /opt/data/cron에 영속). 안전상 기본 paused 권장.
hermes cron create "0 9 * * *" --script produce_cron.sh --no-agent --name produce
hermes cron pause produce          # 큐 채우고 준비되면 resume
# 3) 활성화: hermes cron resume produce
```

- 주제 큐 채우기: `python3 /opt/data/db/topics/topic_queue.py add --topic "..."`.
- 빈 큐/락 점유 시 silent(무출력). 실패는 `error`로 남아 재처리 안 함(사람 점검).
