# Track F97 — Daily 성과 평가: 에이전트 vs S&P500 벤치마크

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F97
- **Title**: Daily 성과 평가 — 에이전트 누적수익 vs S&P500(SPY) buy-and-hold, alpha 표시
- **Type**: feature
- **Status**: merge-awaiting  <!-- active → merge-awaiting (set when Build & Test passes) → merged (by /ai-dlc-merge) -->
- **Branch**: feat/F97
- **Worktree**: .claude/worktrees/F97
- **Submodule branch**: — (monorepo; operator-console/cli 터치 여부는 surface 결정에 따름)
- **Base commit**: 4f3fcbf4a3e40d02dc8c57f30aea59e28b36e190
- **Start Date**: 2026-07-10T10:23:18Z

## Extension Configuration
| Extension | Enabled | Mode | Decided At |
|---|---|---|---|
| Property-Based Testing | Yes | Full (all rules blocking) | Requirements Analysis |
| Security Baseline | No | — | Requirements Analysis |

- **Property-Based Testing**: Enabled (Full). Framework = hypothesis (이미 repo에서 사용 중, PBT-09 충족). 수익률 정규화·alpha 계산 = 순수함수/불변식 대상이라 적합. 노출 코드(TUI/dashboard payload)는 대체로 thin이라 PBT N/A 가능 — 코드생성 단계에서 컴포넌트별 판정.
- **Security Baseline**: Disabled. read-only 로컬 로그 조인 + 기존 대시보드 인증 재사용, 새 시크릿/외부노출 없음.

## Scope
사용자 요청: "autostock을 s&p500에 그냥 넣었을 때 대비 얼마나 잘하고 있는지 daily로 확인".

핵심 발견 (Workspace Detection): 데이터 토대가 이미 존재한다.
- `workspace/equity.jsonl` — EOD마다 계좌 총자산(equity) + SPY/QQQ/^VIX 가격을 한 줄씩 영속화
  (`src/agent/logs/equity.py:record_equity`, `src/trading/modes/agent.py:_eod`에서 호출).
- 재사용 가능한 지표 라이브러리: `src/backtest/metrics.py`(pandas), `src/benchmark/metrics.py`
  (`compute_metrics`/alpha, pure-python).

GAP (이 트랙이 채울 부분):
- SPY 가격을 buy-and-hold 정규화 곡선으로 변환해 에이전트 누적수익 vs S&P500 누적수익 + alpha를 계산하는 코드가 없음.
- 포트폴리오 레벨 벤치마크 비교를 노출하는 surface가 없음(F86 모바일 대시보드 `day_pnl_pct`는 null 플레이스홀더, TUI 스냅샷에 수익률 필드 없음, 스케줄된 성과 리포트 파일 없음).
- F70 `src/benchmark/`는 dormant + 그 baseline은 지수가 아니라 종목 전략이라 이 요청과 다름.

관련 메모: [[f24-decision-quality]] 계열의 per-decision benchmark_excess와는 다른 **포트폴리오 레벨** 지표.

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. `/ai-dlc-merge`가 큐 구성·충돌 해결 시 참조.

- **공유 파일 (주의)**:
  - `src/agent/steering/runtime.py` — `publish_snapshot` snapshot dict에 `perf_vs_benchmark` 1줄 + `_perf_block()` 메서드 추가 (additive). F44 등 이 파일 동시 변경 트랙과 rebase 시 충돌 가능.
  - `scripts/status.py` — `_summary`에 라인 추가 + `_pct_markup`/`_bench_line` 신규.
  - `operator-console/.../server/autostock/dashboard-read.ts` — `DashboardPayload` 계약에 `perf` 필드(F94 최근 수정 파일; base 4f3fcbf에 F94 반영됨).
  - `operator-console/.../app/.../dashboard-source.ts` / `dashboard-view.tsx` / `mobile-shell.tsx` — F86 계약.
  - `operator-console/.../opencode/.../sidebar/autostock.tsx` — 콘솔 사이드바.
  - **agent._eod 는 미변경** (read-time 파생) — 머지 충돌면 감소.
- **API/시그니처 변경**: 없음(전부 additive: 신규 필드/신규 함수). 제거·rename 없음 → 구버전 리더 하위호환.
- **알려진 동시 변경**: F95/F96 (동시 세션이 id 선점, 내용 미상). dashboard/steering 계약을 F95/F96가 건드리면 `perf` 필드/`perf_vs_benchmark` 라인에서 겹칠 수 있음 — 머지 전 재확인.

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard (clarifying questions via UAQ; PBT opt-in)
- [x] User Stories — SKIP (단일 개발자, 명확·단순, 헤드라인 표시)
- [x] Workflow Planning — 실행: Functional Design / Code Gen / Build&Test
- [x] Application Design — SKIP (신규 서비스계층 없음; Functional Design에서 커버)
- [x] Units Generation — SKIP (단일 유닛)
- [x] Functional Design — EXECUTE (read-time 파생; agent._eod 미변경)
- [x] Construction (per-unit Code Generation) — EXECUTE
  - [x] perf-vs-benchmark unit — 코어(performance.py) + 6 surface 배선 + PBT/example 테스트
- [x] Build & Test — 그린 (Python 1503 pass / typecheck 19/19 / TS 28 pass / live smoke). 유일 실패는 F97 무관 워크트리-경로 아티팩트(test_health_publish, main에서 통과)
