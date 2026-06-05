# Execution Plan — F65 하이브리드 회상

> **Track**: F65 · **Phase**: Workflow Planning · **Date**: 2026-06-05

---

## Transformation Scope
- **Type**: Agent capability upgrade (recall quality)
- **Primary Changes**: 상황 지문 조립 → 태그 사전필터+효능정렬(순수) → LLM 재랭크+폴백 →
  `_build_lesson_context` 교체 → EOD decay/은퇴
- **Components**: 신규 `src/agent/intraday/recall.py` (또는 `src/agent/recall.py`),
  `src/agent/prompts.py` (`_build_lesson_context`), `src/agent/orchestrator.py` (주입 경로),
  `src/agent/review.py` 또는 EOD 경로 (decay/은퇴)
- **선행 의존**: **F62 merged** (`lesson_efficacy` API + LessonRecord 태그 필요)

## Change Impact
| Area | Impact | Description |
|------|--------|-------------|
| User-facing | Indirect | 더 관련성 높은 레슨 → 결정 품질 (간접) |
| Structural | Moderate | 회상 모듈 신규, 주입 경로 교체 |
| Data model | Low | F62 태그 소비 (스키마 추가 없음) |
| API/Contract | Low | 내부 함수 시그니처 |
| NFR | Yes | 결정론 격리, 0 new deps, 폴백 안전 |

## Risk Assessment
- **Risk Level**: Moderate — 비결정(LLM 재랭크) 도입; 단 폴백·순수격리로 통제.
- **주의 1**: F62 미머지 시 효능 API 부재 → **머지 순서 강제** (F62 먼저).
- **주의 2**: `prompts.py`를 F61이 동시 변경 → 함수 레벨 분리, F61 머지 후 rebase.
- **주의 3**: LLM 재랭크 비용/지연 → 저빈도 턴 한정 + K' 상한.
- **Rollback**: Easy — worktree 격리; 최악의 경우 `_build_lesson_context`를 recency-only로 복원.

## Stage 선택
| Stage | 결정 | 사유 |
|-------|------|------|
| Requirements | DONE (standard) | requirements.md |
| User Stories | SKIP | 내부 도구 |
| Application Design | FOLD | Functional Design 흡수 |
| Units Generation | SKIP | 단일 유닛 unit-recall |
| Functional Design | EXECUTE | business-logic-model.md |
| NFR Req/Design | FOLD | requirements.md + 결정론/폴백 노트 |
| Infra Design | SKIP | 없음 |
| Code Generation | EXECUTE | F62 머지 후 worktree |
| Build & Test | EXECUTE | pytest + 폴백/회귀 시나리오 |

## Workflow Visualization
```text
[상황 지문(순수)] → [태그 필터 + 효능정렬(순수)] → [LLM 재랭크] →(실패)→ [1차정렬 폴백]
                                  │                       │
                                  └─────── 주입 (_build_lesson_context 대체) ───────┘
                                                  │
                              [EOD: decay/은퇴] ── 무한누적·레짐드리프트 방지
```

## 머지 순서
**F62 → F65 → F64.** 본 트랙은 F62 머지 commit을 base로 분기.
