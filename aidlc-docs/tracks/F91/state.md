# Track F91 — sentiment sweep persistence clock fidelity (wallclock-drift hotfix)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F91
- **Title**: sentiment sweep persistence clock fidelity (wallclock-drift hotfix)
- **Type**: feature (bugfix)
- **Status**: merged → main 5591eca (2026-06-22)  <!-- rebased 1b5eb40→1805ae3 → merged 5591eca -->
- **Branch**: feat/F91
- **Worktree**: .claude/worktrees/F91
- **Submodule branch**: — (monorepo)
- **Base commit**: 1b5eb40 (worktree branch-point)
- **Start Date**: 2026-06-22

## Extension Configuration
- **Security Baseline**: Disabled — N/A (no network/auth/secret/IO surface change; one-line clock threading).
- **Property-Based Testing**: Disabled — N/A (existing example-based tests already cover the date-window invariant; fix made them pass deterministically).

## Scope
`SentimentSweeper._sweep()` persisted via `append_sweep(records, root=...)` **without threading
its injected clock** (`now_fn`). `append_sweep` then fell back to a second, independent
`datetime.now()` to choose the ET-date partition file.

- **Test symptom**: `tests/signals/test_sentiment_sweep.py` (3 cases) injected `now_fn=lambda: ET_NOON`
  (2026-06-12) and asserted with `load_recent(now=ET_NOON)`, but records were written to the *real*
  wallclock date partition (today) → reader looked in the logical-clock partition → empty. Failures
  surfaced once real date drifted away from the hardcoded `ET_NOON` (F88 Build & Test caught them as
  unrelated pre-existing failures).
- **Real bug (production)**: two independent wallclock reads can straddle ET midnight, landing a
  sweep's records in a different ET-date file than the sweep logic used (latent
  [[timeline-midnight-crossing-regions]]-class rollover hazard).

**Fix**: thread the sweep's own clock — `append_sweep(records, root=self._root, ts=now_et)` —
so persistence partitions by the same logical clock the sweep evaluated `_in_window` against.
Single-line change in `src/signals/sentiment_sweep.py`; no API/signature changes (`append_sweep`
already accepted optional `ts`).

## Merge Risk Notes
- **공유 파일**: `src/signals/sentiment_sweep.py` — F88과 무관(F88은 sentiment 파일 미수정). 충돌 없음.
- **API/시그니처 변경**: 없음 (`append_sweep(ts=...)`는 기존 optional 파라미터).
- **알려진 동시 변경**: 없음. 단독 lean bugfix, 단독 머지 가능.

## Stage Progress
- [x] Workspace Detection — brownfield, 기존 코드 수정. 신규 트랙(F88 Build & Test에서 분리).
- [x] Requirements Analysis — minimal (근본원인·수정 범위 본 state.md Scope에 기록).
- [x] User Stories — **skip** (단일 개발자, isolated bugfix, zero user-facing 변화).
- [x] Workflow Planning — lean: Application Design/Units skip, 단일 코드수정+테스트통과.
- [x] Application Design — **skip** (기존 컴포넌트 경계 내 1줄 수정).
- [x] Units Generation — **skip** (단일 단위).
- [x] Construction — `sentiment_sweep.py` `append_sweep(ts=now_et)` 스레딩.
- [x] Build & Test — `tests/signals/test_sentiment_sweep.py` **13 passed** (이전 3 failed→0),
      `tests/signals/` 전체 **165 passed**. build-and-test-summary.md 참조.
