# Build & Test Summary — F22: AI 협업 TUI 개선

## Build Results

### Python (Unit A: daemon-data)
- **Import smoke**: OK (`generate_turn_id`, `build_turn_summary`, `Decision.turn_id`)
- **pip check**: clean (0 new runtime deps)
- **Changed files**: 5 (turn_log.py, journal.py, orchestrator.py, runtime.py, modes/agent.py)

### TypeScript (Unit B: tui-components)
- **bun install**: clean (workspace package linked)
- **tsgo --noEmit**: clean (0 errors)
- **New package**: `packages/tui-trading/` (10 files)
- **Modified**: `packages/opencode/routes/session/index.tsx`, `packages/opencode/package.json`
- **0 new npm dependencies** (catalog: references only)

## Test Results

### Python Unit Tests
| Suite | Tests | Status |
|-------|-------|--------|
| **F22 new: test_turn_log_f22.py** | 16 | PASS |
| **F22 new: test_decision_turn_id.py** | 5 | PASS |
| **F22 new: test_monitor_f22.py** | 7 | PASS |
| **Existing: modified test_sidebar_upgrade.py** | 1 (assertion updated) | PASS |
| **Full regression** | **459** | **ALL PASS** |

### TypeScript
- tsgo typecheck: **CLEAN** (0 errors)

### Critic Review
- 서브에이전트 적대적 검토 완료 (8 findings)
- HIGH 1건 + MED 2건 + LOW 1건 반영
- 핵심 수정: `_correlate_turn` 시계열 매칭 → `started_at` 기반으로 수정 (결정을 올바른 턴에 배정)

## Security Baseline Compliance

| Rule | Status | Notes |
|------|--------|-------|
| SECURITY-03 | PASS | turn_id/summary에 토큰/API키 포함 불가 (결정론적 생성). thesis 파일 경로 검증 (path traversal 방지). |
| SECURITY-10 | N/A | 0 new runtime deps (Python + TS 모두) |
| SECURITY-11 | PASS | 턴 ID 생성은 turn_log 모듈에 격리. 데이터 훅은 읽기 전용. |
| SECURITY-15 | PASS | current_turn try/finally fail-safe. 파일 읽기 실패 시 graceful fallback. |

## PBT (Partial) Compliance

| Rule | Status | Notes |
|------|--------|-------|
| PBT-02 | PASS | `generate_turn_id` 순차 증가 속성 + 타입별 독립 |
| PBT-03 | PASS | `build_turn_summary` 결정론적 속성 (같은 입력→같은 출력) |
| PBT-07~09 | N/A | 비즈니스 로직 없는 UI 컴포넌트 (TS side) |

## Deliverables

### Unit A (Python daemon)
1. `generate_turn_id()` — 타입 접두사 + 날짜 내 순차 ID (R1, I3, W1, E1, C2)
2. `build_turn_summary()` — 결정 기반 자동 1줄 요약
3. `Decision.turn_id` — Optional 필드 (하위호환)
4. `record_turn()` 확장 — turn_id, started_at, summary, health 필드
5. `monitor.json` 구조화 — turns.recent/decisions를 객체 배열로, current_turn + workspace_root 추가
6. `_correlate_turn()` — started_at 기반 시계열 매칭 (critic #1 수정)

### Unit B (TypeScript TUI)
1. `packages/tui-trading/` — 완전 독립 패키지 (10 파일)
2. `TimelineBar` — 2줄 타임라인 바 (마커 + 시간축 + 깜빡임)
3. `TurnOverlay` — 턴 상세 플로팅 패널 (메타 + 요약 + 결정 목록)
4. `SymbolOverlay` — 심볼 논거 플로팅 패널 (포지션 + thesis + 최근 결정)
5. Session 레이아웃 통합 — TimelineBar + 오버레이 배치

## Invariants Maintained
- 거래 경로 (RiskManager→Broker) 무영향
- 기존 steering 기능 (commands, events, snapshot) 무변경
- advisor-only 원칙 유지
- 0 new runtime deps (Python + TS)
