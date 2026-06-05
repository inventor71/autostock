# Execution Plan — F62 귀속/효능 기반

> **Track**: F62
> **Phase**: Workflow Planning
> **Date**: 2026-06-05

---

## Transformation Scope
- **Type**: Additive data/infrastructure layer (enabling for F65/F64)
- **Primary Changes**: Decision/LessonRecord 스키마 확장 → efficacy 순수 집계 → 통계 가드 →
  times_applied 증가 배선
- **Components**: `src/agent/journal.py`, `src/agent/quality/collector.py` (재사용), 신규
  `src/agent/efficacy.py`, 인용 증가 배선 1곳(`orchestrator.py` 또는 executor decision-write 경로)

## Change Impact
| Area | Impact | Description |
|------|--------|-------------|
| User-facing | No | 내부 데이터 레이어 (효능은 후속 트랙이 노출) |
| Structural | Low | 스키마 필드 추가-only |
| Data model | Yes | Decision/LessonRecord 필드 추가 (하위호환 기본값) |
| API/Contract | Low | decisions.jsonl 형상 변경 → golden contract 동기화 확인 |
| NFR | Yes | 결정론, 0 new deps, PBT Partial |

## Risk Assessment
- **Risk Level**: Low — 거래 경로 무관, 추가-only 스키마, 순수 함수.
- **주의 1**: decisions.jsonl 하위호환 (필드 없는 기존 라인) — Pydantic 기본값으로 해소, 회귀 테스트 필수.
- **주의 2**: F24 collector 재사용 시 그 내부 매칭 휴리스틱(`_heuristic_match`)에 효능이 종속 →
  매칭 한계를 효능 문서에 명시.
- **Rollback**: Easy — worktree 격리, merge 전 main 무영향.

## Stage 선택
| Stage | 결정 | 사유 |
|-------|------|------|
| Reverse Engineering | SKIP | 브라운필드, 타깃(journal/quality) 직전 토론서 분석됨 |
| Requirements | DONE (standard) | requirements.md |
| User Stories | SKIP | 내부 인프라 |
| Workflow Planning | DONE | 본 문서 |
| Application Design | FOLD | 신규 컴포넌트 1개 → Functional Design에 흡수 |
| Units Generation | SKIP | 단일 유닛 unit-attribution |
| Functional Design | EXECUTE | business-logic-model.md |
| NFR Req/Design | FOLD | requirements.md NFR 섹션 + 결정론/PBT 노트 |
| Infrastructure Design | SKIP | infra 변경 없음 |
| Code Generation | EXECUTE | worktree |
| Build & Test | EXECUTE | pytest + PBT |

## Workflow Visualization
```text
[schema 확장] ──> [efficacy.py 순수집계] ──> [통계 가드] ──> [times_applied 배선]
   (journal.py)        (collector 재사용)       (순수)          (인용 시 +1)
        │                     │                   │                  │
        └──── 하위호환 회귀 ───┴──── PBT(직렬화/단조/경계) ───────────┘
                                   │
                            [Build & Test green] ──> merge-awaiting
```

## 머지 순서
**F62 먼저.** 머지 후 F65가 e8b112b+F62 위에서 분기(효능 소비), 이어 F64가 F65 위에서 분기.
