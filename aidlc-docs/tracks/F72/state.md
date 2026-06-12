# Track F72 — Research 스크리닝 결과 로깅 + TUI 노출

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F72
- **Title**: research turn 스크리닝→필터링 결과(검토 종목 + 패스 사유)를 로깅하고 operator TUI(steer_read)에서 조회 가능하게
- **Type**: feature
- **Status**: merge-awaiting  <!-- critic round 반영 + 재검증 green 2026-06-12 -->
- **Branch**: feat/F72
- **Worktree**: .claude/worktrees/F72
- **Submodule branch**: — (monorepo; operator-console/src는 메인 repo, cli 서브모듈 무접촉)
- **Base commit**: 76ff7b6
- **Start Date**: 2026-06-11

## Extension Configuration
- **Security Baseline**: Enabled — 적용: SECURITY-03/05/15 (로깅·날짜 인자 검증·fail-safe), 나머지 N/A (신규 endpoint/인증/암호화/인프라 변경 없음)
- **Property-Based Testing**: Enabled (Partial) — 레코드 직렬화 round-trip + 날짜 인자 검증 property test, 그 외 예제 기반

## Scope
research turn에서 에이전트가 유니버스(131심볼)를 스크리닝→필터링한 결과가 현재
decisions/thesis(소수 종목)로만 남고, "어떤 종목이 검토되고 왜 패스됐는지"는
LLM 턴 컨텍스트에서 휘발됨. 이를 구조화 로깅하고 operator TUI(steer_read 채널)로
조회 가능하게 한다. 관련: [[f61-market-signals]] (scoreboard/movers 도구).

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성.

- **공유 파일 (주의)**: `src/agent/prompts.py` (research 프롬프트 — 프롬프트 트랙과 충돌 소지), `operator-console/src/{schema,parser,steer-handler,filedrop,mcp-server}.ts`
- **API/시그니처 변경**: TS `SteeringVerb` union에서 `thesis`/`theses` 제거 + `ALL_VERBS`에서 제거 (read verb는 union 비포함이 규약 — contract.test 복구). `SteeringEvent.kind`/`ALL_EVENT_KINDS`에 `exec_outcome` 추가. Python 측 시그니처 변경 없음(신규 모듈 `src/agent/screening_log.py` 추가만).
- **알려진 동시 변경**: F71 (모바일 앱 — opencode/cli 측이라 겹침 낮음)

## Stage Progress
- [x] Workspace Detection — brownfield, codekb 존재 → RE skip
- [x] Requirements Analysis — standard (승인 2026-06-11)
- [x] User Stories — SKIP (단일 운영자 페르소나, 수용기준은 requirements §7)
- [x] Workflow Planning — 승인 2026-06-11
- [x] Application Design — SKIP (기존 컴포넌트 경계 내)
- [x] Units Generation — SKIP (단일 유닛 "screening")
- [x] Construction — unit "screening"
  - [x] Functional Design — 승인 2026-06-11
  - [x] Code Generation Part 1 (계획)
  - [x] Code Generation Part 2 — 구현+테스트, 커밋 47fa1e8
- [x] Build & Test — ALL GREEN (py 1054→critic round 후 1057, console 168, live smoke) + post-merge guide
- [x] Critic round — HIGH 1(부분스캔 클로버)·MEDIUM 2(날짜 키 분리, screening/ 미생성) 반영
