# 시사베테랑 작가 (siasa) — 작업물 정리

Hermes 시사베테랑 작가 구축 중 생성한 코드·산출물을 케이스별로 정리한 디렉터리.
(hermes-agent 프레임워크 파일과 분리)

## 구조

| 폴더 | 내용 |
|------|------|
| `writer/` | **프로덕션 파이프라인** — script_guard·siasa_writer·numeric_gate·generate_script + 테스트(31개 GREEN). import 위해 함께 둠 |
| `training/` | QLoRA 학습 — prepare_training_data·train_qlora·verify_lora·train.jsonl(39쌍) |
| `experiments/` | 케이스별 탐색·진단 (아래) |
| `deploy/` | merge_lora (LoRA→16bit merge) |
| `samples/v1_broken/` | v1 깨진 산출물(퇴화 루프·`(참고)`도배) — verify_out 등 |
| `samples/v2/` | v2 발행급 산출물 — writer_T0~2(4.2~4.7K), demo_대본+review 등 |
| `adapters/` | siasa_lora(v1·3ep), **siasa_lora_e6(채택·6ep)** |

### experiments/ 케이스
- `vram/` — 16GB 적합성(unsloth load peak)
- `diagnostics/` — EOS 정지 진단(diag_stop): gemma4 eos=`<turn|>`106 발견
- `gen_sweep/` — 다중시드 gen config 스윕(퇴화 해결: eos106/rep1.3/ng8)
- `length/` — 분량 천장 탐색: 이어쓰기/재작성=~2.5K천장, **아웃라인 스캐폴딩=4K+ 돌파**
- `injection/` — 수치 주입 프로브(신뢰불가 확정)
- `eval/` — e6 검증·작가 파이프라인 검증(3/3 구조게이트 통과)

## v2 결과 요약
- 생성 안정성(퇴화·클로징·분량) 해결. 형식=발행급(한글숫자·마크다운0).
- **단 수치 정확도 미보장** — `numeric_gate` 체크리스트로 발행 전 사람 전수검수 필수.
- 상세: `plans/20260614-1215-hermes-siasa-agent.md`

## 운영 노트
- **배포**: GPU writer 서비스 = `ai-source-builder/services/writer/`(이 모듈들의 **복사본** 사용). gemma4가 신규라 llama.cpp·Ollama GGUF 변환 둘 다 미지원 → transformers 서비스+gateway `/v1/writer` 경로.
- writer 서비스 LoRA 마운트 경로 = `siasa/adapters/siasa_lora_e6`.
- `experiments/`·`training/` 스크립트는 이동 전 하드코딩 경로(`/.../ai-movie-hermes-agent/...`) 보유 — 재실행 시 경로 갱신 필요(역사적 기록용).
- `siasa_merged_16bit`(23GB, 루트): Ollama import 실패물 → **삭제 가능**(writer 서비스는 base+LoRA 4bit 사용).
