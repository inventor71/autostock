# Track F94 — 콘솔(operator-console) 읽기 툴 provider 정합성 (F92 TS판 후속)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F94
- **Title**: 콘솔 계좌-truth 읽기 툴 provider 정합성 (account_farm일 때 데몬 snapshot 경유)
- **Type**: bugfix (F92 후속 — TS 콘솔 경로)
- **Status**: merged → main ae853d6 (2026-07-05)  <!-- rebase onto main(e314a6f): aidlc-state.md 충돌만(F93 active→merged) 해결; verify 재실행 account-truth+alpaca-data 29 pass/0 fail; 전체 174 pass, 유일 실패 launcher-f71=fast-check 미설치(F94 무관) -->
- **Branch**: feat/F94
- **Worktree**: .claude/worktrees/F94
- **Submodule branch**: — (monorepo; operator-console 포함)
- **Base commit**: 940a99e
- **Start Date**: 2026-06-29

## Extension Configuration
- **Security Baseline**: Disabled (내부 정합성 버그, 신규 공격면 없음)
- **Property-Based Testing**: Disabled (배선 변경 중심)

## Scope
F92는 Python 데몬/CLI broker-truth를 provider-aware `create_broker`로 통일했으나 sweep이
Python만 훑어 **TypeScript 콘솔 경로**를 놓쳤다. operator-console의 채팅 "live" 계좌-read
툴이 `operator-console/src/alpaca-data.ts`(ALPACA_API_KEY → paper-api.alpaca.markets 직결)로
Alpaca 계좌를 직접 읽어, account_farm 인스턴스에서 자기 sub-account가 아니라 공유 Alpaca
계좌(유령 RTX/TMO)를 보고한다. 사이드바(snapshot.json=account_farm 진실)와 불일치.

영향 지점(전수 점검 결과 — `mcp-server.ts`가 유일한 Alpaca-직결 계좌-read 경로):
- 계좌-truth(provider-sensitive, 수정 대상): `getAccountInfo`(263), `getAllPositions`(273),
  `getOpenPosition`(285), `getPortfolioHistory`(299), `getOrders`(365)
- 시장데이터/참조(계좌무관, 유지): assets/calendar/clock + stock bars/quote/trade/snapshot
- mutating(close_position/close_all_positions/cancel_order)은 `handleStructured→FileDrop→데몬`
  경유라 account_farm로 올바르게 감 — 안전, 변경 없음
- dashboard-read.ts / webauthn.ts는 snapshot.json 경유(또는 Alpaca client 미사용) — 정상

목표: account_farm일 때 계좌-truth 읽기 툴을 **데몬 snapshot.json(account_farm 진실)** 경유로,
alpaca일 때만 Alpaca 직결 유지. 시장데이터는 Alpaca 직결 유지. [[risk-execution-redesign]]

## Merge Risk Notes
- **공유 파일**: `operator-console/src/mcp-server.ts`, `operator-console/src/alpaca-data.ts`
  (F93 모바일 트랙이 operator-console을 건드릴 수 있음 — 머지 시 확인)
- **API/시그니처**: 신규 provider 분기/리더 추가 (기존 시그니처 보존)
- **알려진 동시 변경**: F93(모바일, operator-console serve/routes) — 파일 겹침 가능

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard
- [x] User Stories — skip (내부 정합성 버그)
- [x] Workflow Planning
- [x] Application Design — skip (기존 툴 배선 변경, 신규 컴포넌트 없음)
- [x] Units Generation — skip (단일 단위)
- [x] Construction (Code Generation)
  - [x] Unit-1 콘솔 계좌-read provider-aware (코드+테스트 green, 실데이터 검증)
- [x] Build & Test (operator-console/test 187 pass; post-merge-guide 작성)
