# db/topics — 주제 큐 (자율 제작 work-list)

자율 제작(cron)이 소비하는 **기계용 작업목록**. 사람/trend-researcher가 주제를 채우고 cron이 pop.
**db/decisions(사람 go/no-go 판정)와 분리** — 여기는 미가공 work-list다.

## 스키마 (`queue.jsonl`, jsonl)

| 필드 | 내용 |
|------|------|
| `id` | 순번(max+1) |
| `date` | 추가 날짜 |
| `topic` | 주제 |
| `angle` | (선택) 앵글 |
| `type` | A/B/C (현행 C) |
| `status` | `pending`→`in_progress`→`done`/`error` |

## 상태기계

- `pending`: 대기. cron이 가장 오래된 pending을 pop.
- `in_progress`: cron이 pop해 생성 중(중복 pop 방지).
- `done`: 생성 성공.
- `error`: 생성 실패(재처리 안 함 — 사람이 점검).

## 사용

```bash
python3 topic_queue.py add --topic "환율 급등" --angle "장바구니 물가"   # 주제 추가
python3 topic_queue.py list                                             # 전체 보기
```

- `pop_next()`/`mark(id,status)`는 cron 래퍼(`siasa/orchestrator/cron_produce.py`)가 사용.
- 경계 검증(주제 필수·타입 A/B/C) + NFC 정규화.
