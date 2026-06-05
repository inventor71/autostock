# Build & Test Summary — F65 하이브리드 회상

> **Track**: F65 · **Date**: 2026-06-05 · **Branch**: feat/F65 @ b80656b (base f54d018 = F62)
> **스택**: F62 위 분기 (미머지). 머지 전 F62/F65/F64 일괄 검수 예정.

## 결과: ✅ PASS
- **전체 pytest: 838 passed** (F62 824 + recall 14), 0 fail, 0 회귀.
- import 클린 (recall/prompts/orchestrator). **0 new deps.**

## 구현 (단일 유닛 unit-recall)
| 파일 | 변경 |
|------|------|
| `src/agent/recall.py` (신규) | SituationFingerprint·build_fingerprint·prefilter_and_rank·recall_lessons·build_lesson_context·mark_retirements |
| `src/agent/prompts.py` | `_build_lesson_context` → recall 위임 (**lesson_id 렌더** — critic fix) |
| `src/agent/orchestrator.py` | `_get_lessons` → 상황 recall; `_lesson_efficacy` 일캐시 fail-safe |

## 테스트 (tests/test_recall.py — 14건)
- 지문 조립(첫 실라인·dedup), 검증 레슨이 미검증 행운 레슨보다 상위(효능 캡), regime 매칭 가산,
  결정론 tie-break, exclude.
- recall 폴백: rerank None→순수 top-k; valid→재정렬; **raise→폴백; junk id→폴백(빈손 아님)**.
- build_lesson_context **lesson_id 포함** 검증; 은퇴(검증-음성/유휴); PBT(≤k, never raise).

## v1 스코프 편차 (정직 — 검수 시 확인)
1. **LLM 재랭크 OFF (결정론 순수 순위)**: `recall_lessons`는 `rerank_fn` 주입+graceful 폴백을
   지원하나, orchestrator는 v1에서 rerank_fn=None로 호출(순수 prefilter 순위). LLM 재랭크 턴
   활성화는 인터페이스만 마련(문서화된 활성화 지점). → "하이브리드"의 LLM 단계는 아직 미활성.
2. **은퇴 지속화 미구현**: `mark_retirements`는 순수(은퇴 id 반환)까지. lessons.jsonl에 retired
   플래그 rewrite(EOD)는 follow-up — 현재는 반환 id를 `recall_lessons(exclude=...)`로 적용 가능.
3. **효능 일캐시**: 첫 research 턴에서 `collect_outcomes`(yfinance) 1회 호출(일 단위 캐시).
   실패 시 {}로 폴백 → recency/관련성 랭킹(턴 안 죽음).

## critic 반영 검증
- MED(lesson_id 미렌더 → 인용 불가): build_lesson_context가 `[L007]` 렌더 — 테스트 확인.
- MED(regime/sector 미태깅): F62에서 lesson 도구 태깅 추가(선행); 미태깅 레슨은 관련성 0 중립 — 폴백 안전.

## Status
Build & Test PASS → `merge-awaiting`. 단 위 v1 편차(특히 #1 LLM 재랭크 미활성)는 검수 시 판단 필요.
