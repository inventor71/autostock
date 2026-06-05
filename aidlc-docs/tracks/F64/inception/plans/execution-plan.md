# Execution Plan — F64 헌장 경계 자가재작성

> **Track**: F64 · **Phase**: Workflow Planning · **Date**: 2026-06-05

---

## Transformation Scope
- **Type**: Agent self-improvement engine (high-risk, but isolated by immutable boundary)
- **Primary Changes**: 헌장 상수+체크섬 → 2층 프롬프트 조립 → 컴플라이언스 검증(순수) →
  버전/lineage(prompt_manager 재사용) + 즉시교체 → 자동 롤백(F62 효능) → EOD 재작성 스텝
- **Components**: 신규 `src/agent/constitution.py`, 신규 self-rewrite 모듈
  (`src/agent/self_rewrite.py`), `src/agent/prompts.py` (2층 조립),
  `src/strategy/llm/prompt_manager.py` (PromptVersion/lineage 재사용), EOD 경로(review/orchestrator)
- **선행 의존**: **F62 merged** (효능/롤백 메트릭) + **F65 merged** (회상; prompts.py 조립 정합)

## Change Impact
| Area | Impact | Description |
|------|--------|-------------|
| User-facing | Low | 헌장 승인(드물게), self-rewrite rejected 통지 |
| Structural | Yes | 프롬프트 2층 조립, 자가재작성 루프 신규 |
| Data model | Low | PromptVersion lineage (prompt_manager) |
| API/Contract | Low | 내부 모듈; steering 이벤트 1종(거부 통지) 추가 가능 |
| NFR | Yes | fail-closed, 결정론 격리, 감사성, 0 new deps |

## Risk Assessment
- **Risk Level**: High (자기수정 루프) — 그러나 실행경로 불변(코드) + 컴플라이언스 + 롤백으로 격리.
- **남는 리스크(사용자 감수)**: 헌장 준수하나 나쁜 세대가 롤백 전 N일 라이브; 다세대 누적 드리프트
  (→ FR-5.3 원본 시드 회귀 점검); 레짐 행운 박제(→ excess 기준).
- **주의(머지)**: prompts.py를 F61/F65도 변경 → 함수 레벨 분리 + 머지 순서 F62→F65→F64 준수.
- **Rollback(트랙)**: Easy — worktree 격리; 최악의 경우 자가재작성 비활성 플래그로 seed 고정.

## Stage 선택
| Stage | 결정 | 사유 |
|-------|------|------|
| Requirements | DONE (comprehensive) | requirements.md |
| User Stories | SKIP | 단일 운영자 (헌장 승인 워크플로는 FR-7) |
| Application Design | FOLD | Functional Design 흡수 |
| Units Generation | SKIP | 단일 유닛 unit-self-rewrite |
| Functional Design | EXECUTE | business-logic-model.md + constitution.md |
| NFR Req/Design | FOLD | requirements.md NFR + fail-closed 노트 |
| Infra Design | SKIP | 없음 |
| Code Generation | EXECUTE | F65 머지 후 worktree |
| Build & Test | EXECUTE | pytest + PBT + 컴플라이언스/롤백 음성 테스트 |

## Workflow Visualization
```text
        ┌───────────── 불변 헌장 (코드, 사용자 승인으로만 변경) ─────────────┐
        │                  prepend, write 불가                              │
        ▼                                                                   │
[EOD: 효능(F62) 읽기] → [진화 섹션 재작성(LLM)] → [컴플라이언스 검증(순수)]    │
                                                      │ pass        │ fail   │
                                                      ▼             ▼        │
                                          [변경량캡/쿨다운 OK?] → [거부+이전유지+통지]
                                                      │ yes
                                                      ▼
                                          [즉시 교체 + lineage 기록]
                                                      │
                                  [N일 후 excess 악화?] → yes → [자동 parent 롤백]
                                                      │
                                  [주기적: 원본 시드 대비 드리프트 점검]
```

## 머지 순서
**F62 → F65 → F64.** 본 트랙은 F65 머지 commit을 base로 분기 (에픽의 마지막).
