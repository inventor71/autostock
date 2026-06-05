# Track F59 — 운영자 `/short`·`/cover` shorthand (F54 follow-up)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F59
- **Title**: 운영자 콘솔 `/short`·`/cover` shorthand — F54 숏 후속 (verb 대칭 + footgun 해소)
- **Type**: feature
- **Status**: merged → main 88f6edf (2026-06-05)
- **Branch**: feat/F59
- **Worktree**: .claude/worktrees/F59
- **Submodule branch**: — (opencode fork: parser/schema 변경 포함)
- **Base commit**: d988a65
- **Start Date**: 2026-06-04T00:00:00Z

## Extension Configuration
- **Security Baseline**: Enabled — SECURITY-15 (fail-closed: 숏 명령도 receive_human_order 게이트 통과, 손절 필수). SECURITY-03 (no secrets in logs).
- **Property-Based Testing**: Partial — Hypothesis. 해당 시 parser round-trip.

## Scope
F54에서 닫힌 숏 기능의 후속. 운영자 콘솔에 `/short SYM <N$|Nsh>`(=SELL_SHORT 진입)와
`/cover SYM <N%|Nsh|N$>`(=BUY_TO_COVER 청산) shorthand 추가. `/buy`·`/sell`(롱)과 대칭이 되어
`/sell`을 숏 명령으로 오해하는 footgun 제거. 진짜 공매도(티커 차입·매도) 유지 — 인버스 ETF 아님.
[[risk-execution-redesign]] 게이트(receive_human_order, F54에서 SELL_SHORT/BUY_TO_COVER 확장됨)를 그대로 사용.
critic(F54 R2) #4 지적의 해소 트랙.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/agent/steering/commands.py`, `src/agent/steering/records.py`,
  `operator-console/src/parser.ts`, `operator-console/src/schema.ts`, opencode fork ui-legend.
- **API/시그니처 변경**: SteeringVerb에 `short`/`cover` 추가 (추가만, 기존 verb 불변).
- **알려진 동시 변경**: 없음 (F54 머지 완료, 다른 활성 트랙 F30/F55/F58은 무관 영역).
- **선행 주의**: F54 머지 시점 main 기준 cross-language contract 테스트(event-kinds/verb-set)가
  이미 red(기존 드리프트). verb 추가 시 TS+Python golden 동기화 필요 — 이 트랙이 verb-set는 정상화 가능.

## Stage Progress
- [x] Workspace Detection — reused (brownfield)
- [x] Requirements — minimal (verb 결정 사용자 확정: 진짜 공매도 + /short·/cover)
- [x] User Stories — SKIP (단일 운영자, 기존 verb 패턴 확장)
- [x] Workflow Planning — single unit, Functional Design folded
- [x] Construction (Code Generation) — COMPLETE 2026-06-04
  - Python: `build_human_short` + `_v_short`/`_v_cover` (commands.py), SteeringVerb short/cover (records.py), `_KIND`
  - TS: parser.ts /short·/cover, schema.ts SteeringVerb/ALL_VERBS/TRADE_VERBS, golden regenerated, steer-handler comment
  - Routes through F54 `receive_human_order` gate (mandatory stop etc.) — no new gate logic
- [x] Build & Test — PASSED 2026-06-04
  - Python full suite 794 green (+9 F59: build_human_short ×3, /short ×2, /cover ×2, contract regen)
  - TS: parser.test 14/14, sidebar-format 10/10; operator-console test/ only 2 PRE-EXISTING contract
    failures (thesis/theses verb-set + exec_outcome event-kind — drift on main, NOT F59; short/cover balanced both sides)
  - cli typecheck unaffected (changes in operator-console/src, validated by passing imports/tests)
  - 0 new runtime deps
  - Status → merge-awaiting
