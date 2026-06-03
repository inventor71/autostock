# F25 타임라인 바 개선 — Workflow Planning (실행 계획)

> Requirements 승인 (2026-06-01). 본 계획은 INCEPTION 잔여 + CONSTRUCTION 단계 결정.

## 위험도 평가
**Low–Medium**. UI/표시 레이어 변경이 주이고, 주문/리스크 경로(advisor-only gate)는 건드리지 않음.
- daemon 변경은 monitor.json 직렬화(읽기 전용 집계)에 한정 — 거래 로직 무영향.
- 서브모듈(opencode TUI) 변경은 격리된 `tui-trading` 패키지 + session/index.tsx 통합부.
- 롤백 쉬움 (worktree/브랜치).

## 기존 자산 재사용
- `InterventionRecord` (records.py) — `ts/kind/command/args/outcome/detail` 이미 충분. FR-3에 새 기록 불필요, **읽기만**.
- `AlpacaBroker.is_market_open` + Alpaca `get_clock()` (next_open/next_close) — 마켓 경계 데이터 소스.
- `zoneinfo America/New_York` — DST-aware ET 계산 (scheduler가 이미 US/Eastern 사용).
- F22 `tui-trading` 패키지 구조 (TimelineBar/overlay/hooks/timeline-layout) — 확장 대상.
- F22 monitor.json 파이프라인 (`_turns_summary`, `useMonitorData`) — 확장 대상.

## 단계 결정

| Stage | 결정 | 사유 |
|-------|------|------|
| User Stories | **SKIP** | 단일 운영자 도구, FR로 워크플로 충분 (F22와 동일) |
| Workflow Planning | 진행 중 | — |
| Application Design | **SKIP** | 새 컴포넌트 집합 작음 → Functional Design에 흡수 |
| Units Generation | **EXECUTE (minimal)** | 2개 언어(Python/TS) + monitor.json seam → 2 units |
| Functional Design | **EXECUTE** (per-unit) | 12h 창 경계/자정넘김 세션 모델/날짜조회 경로 등 미해결 확정 필요 |
| NFR Requirements | Unit A SKIP / Unit B 최소 | 0 new runtime dep 예상 (stdlib zoneinfo + 기존 TS) |
| NFR Design | 최소 | 폴링/직렬화 패턴 기존 답습 |
| Infrastructure Design | **SKIP** | 로컬 daemon, 인프라 없음 |
| Code Generation | **EXECUTE** (per-unit) | — |
| Build & Test | **EXECUTE** | 회귀 + 신규 PBT (시간대 변환/세션 경계 pure fn) |

## Units (2개)

### Unit A — `daemon-timeline` (Python, FIRST)
monitor.json을 F25 요구에 맞게 확장:
- **Market hours 블록**: `AlpacaBroker.get_clock()` + zoneinfo로 pre/regular/after 경계 + DST-aware ET 시각을 ISO/UTC로 monitor.json에 게시. (`runtime.py`, `modes/agent.py`)
- **Date-filtered turns**: `_turns_summary`가 임의 ET date 파라미터로 turns.jsonl 필터링. 과거 날짜 조회 경로(FD에서 monitor.json 확장 vs 별도 read 채널 확정). (`runtime.py`)
- **Interventions 블록**: `human_directives.jsonl` 읽어 거래성 명령(buy/sell/flatten/cancel)만 필터 → `{ts, verb, symbol, outcome, detail}`. (`runtime.py`)
- 파일: `src/agent/steering/runtime.py`, `src/trading/modes/agent.py`, (필요 시) `src/execution/brokers/alpaca_broker.py` 마켓 클락 헬퍼.

### Unit B — `timeline-ui` (TypeScript, SECOND, 서브모듈)
`tui-trading` 패키지 + session 통합부 확장:
- **12h 정규장 중심 layout**: `timeline-layout.ts` — 하드코딩 제거, monitor.json market hours 수신, 12h 창 계산, 로컬 시간(KST) 변환.
- **3-구간 배경 + 경계선**: `timeline-bar.tsx` — pre/regular/after 배경 구분 + open/close 경계선.
- **날짜 네비게이션**: 키보드(`← → T`) + 마우스(`< Today >`) 버튼 + `/timeline <date>` slash command (session/index.tsx).
- **Human intervention 마커**: 거래 마커 glyph/색상 (`format.ts`, `types.ts`), 클릭 시 overlay.
- **다가올 세션 기본값**: 장 마감 시 다음 세션 빈 바.
- 파일: `tui-trading/src/{utils/timeline-layout.ts, components/timeline-bar.tsx, components/intervention-overlay.tsx(신규), utils/format.ts, types.ts, hooks/use-monitor-data.ts}`, `packages/opencode/.../session/index.tsx`.

**의존 순서**: Unit A(데이터 계약) → Unit B(UI 소비). Unit B는 Unit A의 monitor.json 스키마에 의존.

## Extensions
- Security Baseline: SECURITY-03(직렬화 시 토큰/시크릿 제외 — intervention args에서 token strip 확인), SECURITY-15(시간대 변환/파일 읽기 fail-safe).
- PBT Partial: 시간대 변환·12h 창 경계·세션 묶음 등 pure function (Hypothesis Python / fast-check TS).

## 워크트리
- Code Gen Part 2 진입 시 `scripts/worktree-setup.sh F25 --ts` (서브모듈 브랜치 + bun install).
- 서브모듈 `operator-console/cli`에서 `feat/F25` 브랜치, 부모 gitlink는 머지 시점에만.
