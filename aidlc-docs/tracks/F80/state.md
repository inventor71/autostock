# Track F80 — JSONL/CSV → Parquet 저장 후보 평가 및 전환

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F80
- **Title**: JSONL/CSV → Parquet 저장 후보 평가 및 전환
- **Type**: feature (storage/infra; intraday store는 behavior-preserving swap)
- **Status**: merge-awaiting  <!-- Build & Test green 2026-06-13 → /ai-dlc-merge -->
- **Branch**: feat/F80
- **Worktree**: .claude/worktrees/F80
- **Submodule branch**: — (monorepo)
- **Base commit**: 01ced61
- **Start Date**: 2026-06-13T09:18:32Z

## Extension Configuration
- **Security Baseline**: Disabled (N/A) — gitignored 비민감 시장 피처 저장, 자격증명/외부입력 경계 없음
- **Property-Based Testing**: Enabled (Full) — framework: hypothesis (이미 설치/광범위 사용).
  적용 property: PBT-02 Round-trip(upsert→read 값/타입 보존), Idempotence((date,symbol)
  last-write-wins, 재upsert 무중복), Invariant(read 반환 FEATURE_COLUMNS 순서/개수 보존).
  PBT-06(stateful) N/A.

## Scope
autostock가 디스크에 적재하는 append-only 데이터 스토어들을 점검해 Parquet로
저장하는 게 실익 있는 대상을 선별하고, 선별된 대상을 전환한다.

조사 결과(요약):
- **최강 후보**: `data/intraday/*.csv` (IntradayFeatureStore) — 코드에 이미
  "a Parquet/DuckDB backend can replace the body later without touching callers"로
  설계된 swap point. 컬럼형 수치 피처, symbol당 1파일, read-all 분석 패턴, 누적 증가.
- **약한 후보(소용량, 분석 로그)**: `workspace/turns.jsonl`(372K), surge history/analyses,
  benchmark equity/metrics, equity/trades, signals records, screening verdicts.
- **부적합(IPC/live-tail/torn-safe append)**: steering commands/events, decisions,
  watch, agent_questions, execution_log/outcomes — Parquet는 append/증분 tail read
  불가라 유지 권장.
- pyarrow는 현재 미설치(pandas만 있음) → Parquet 채택 시 의존성 추가 필요.

관련: [[f61-market-signals]] (intraday/signals), R10(intraday 서브패키지화).

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성.

- **공유 파일 (주의)**: `src/data/intraday/store.py`, `pyproject.toml` (deps), `.gitignore`
- **API/시그니처 변경**: IntradayFeatureStore 공개 contract(upsert/read)는 유지(swap point)
- **알려진 동시 변경**: 없음(예상)

## Stage Progress
- [x] Workspace Detection — brownfield, codekb 존재, 활성 트랙 다수(독립 영역)
- [x] Requirements Analysis — standard (scope 확정: intraday store만, Parquet 단독 + 1회 CSV 마이그레이트)
- [x] User Stories — skip (운영자 비가시 내부 스토리지 변경)
- [x] Workflow Planning — 승인됨 2026-06-13
- [x] Application Design — skip (기존 컴포넌트 경계 내)
- [x] Units Generation — skip (단일 단위)
- [x] Construction (per-unit Code Generation)
  - [x] Parquet 전환 — store.py 본문 교체 + pyarrow + 1회 CSV 마이그레이션 (lazy `_migrate_legacy`)
- [x] Build & Test — 23/23 intraday GREEN (PBT+migration 포함), 실데이터 AAPL 647행 0 mismatch.
      전체 스위트 4 fail은 F80 무관(선존 sentiment 3 + worktree env health 1).
