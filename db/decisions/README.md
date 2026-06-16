# db/decisions — 의사결정 DB

콘텐츠(주제) 의사결정의 **감사 추적**이자 **cron 회고(시스템 자가진화)의 입력**.
DB-first(마스터플랜): AI용 데이터는 **필드 분절**(혼합 비고 금지). append 로그(rebuild 아님) — 결정 1건 = 1줄.

## 스키마 (`decisions.jsonl`, jsonl)

| 필드 | 내용 |
|------|------|
| `date` | 결정 날짜 (YYYY-MM-DD) |
| `topic` | 주제 |
| `type` | A/B/C (현행 전부 C 맥락해설형) |
| `reason` | 이유 (왜 이 결정) |
| `result` | 결과 — **결정 시점엔 비고, 후속 기입**(발행/보류/조회수 등) |

## 사용

```bash
python3 append_decision.py --topic "환율 급등" --reason "시의성 높음" [--type C] [--result 발행] [--date YYYY-MM-DD]
```

- `make_decision_record`가 경계 검증(주제·이유 필수, 타입 A/B/C) + NFC 정규화.
- `load_decisions()`로 전체 로드(회고용).
- `result`는 나중에 같은 주제 줄을 갱신하거나 새 줄로 결과를 남긴다(운영 선택).

## 비고

- **콘텐츠 결정용**(어떤 주제로 영상을 만들지), 프로세스 결정 아님.
- 입력 주체 = 디렉터/trend-researcher(향후). **cron 회고 루프(자가진화)는 자율성 미검증 → 별도.**
