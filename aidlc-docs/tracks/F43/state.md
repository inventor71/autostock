# Track F43 — 데몬 코드 버전 스큐 자가치유 (autostock 런처)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F43
- **Title**: 데몬 코드 버전 스큐 자가치유 — autostock 런처가 구버전 데몬을 감지해 자동 재시작
- **Type**: feature
- **Status**: merge-awaiting  <!-- active → merge-awaiting (set when Build & Test passes) → merged (by /ai-dlc-merge) -->
- **Branch**: feat/F43
- **Worktree**: .claude/worktrees/F43
- **Submodule branch**: — (monorepo, post-F35; operator-console/launcher 는 in-repo)
- **Base commit**: 777cf40
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Enabled — applicable: SECURITY-03(스냅샷에 토큰/시크릿 미기록; code_version=SHA만), SECURITY-01(서브프로세스 인자 고정 — `git rev-parse HEAD`, 셸 인터폴레이션 없음). N/A: 인증/네트워크/입력검증(로컬 파일·systemctl 경로뿐).
- **Property-Based Testing**: Disabled — 분기 로직이 작고 예제기반 단위테스트로 충분(스큐 있음/없음/미스탬프/HEAD 미상).

## Scope
오늘의 버그(`steering: skipping unparseable command line` 무한 반복)의 운영 근본원인 =
**데몬 프로세스가 머지된 새 코드를 자동으로 집어가지 않음**. 데몬은 기동 시점의 인메모리
코드를 계속 들고 돌아서, 오퍼레이터 콘솔(신버전)이 보낸 새 verb(`research`, F38)를 구버전
`SteeringVerb` Literal로 거부함. 데몬은 건강하게 snapshot을 발행 중이라 F14 wedge 자가치유는
트리거되지 않음([[f14-daemon-wedge-selfheal]]).

이 트랙은 **버전 스큐 자가치유**만 추가한다(채널 견고화는 별도 트랙으로 남김 — 사용자 결정):
1. **데몬(Python)**: 기동 시 git HEAD SHA를 1회 resolve → 매 snapshot 발행 페이로드에
   `code_version` 으로 스탬프. ([[console-native-launcher]] 의 snapshot 헬스 신호에 얹음)
2. **런처(`operator-console/launcher/daemon.ts`)**: `ensureRunning()` 의
   `isFreshNow()→attach` 분기에서, attach 직전에 snapshot의 `code_version` vs 작업트리 HEAD
   SHA(`git -C <autostockRoot> rev-parse HEAD`)를 비교. **다르면 무조건 즉시 `systemctl
   restart` → health-wait → attach** (사용자 결정: 게이팅 없음, in-flight turn 보호 안 함).
3. **안전판(restart 루프 방지, fail-open)**: 런처가 자기쪽 HEAD SHA를 못 구하면 스큐 검사를
   건너뛰고 기존처럼 attach. snapshot에 `code_version`이 아예 없으면(= 분명한 pre-F43 구데몬)
   1회 재시작 후 신데몬이 스탬프하므로 수렴.

비목표(Non-goals): 채널 파싱 실패 무한로그/사일런트-노옵 수정(별도 트랙), 수동 실행 데몬
(systemd 밖) 대응, 머지 외 임의 코드편집 감지.

## Stage Progress
- [x] Workspace Detection — brownfield; 기존 launcher/steering 코드 존재
- [x] Requirements Analysis — minimal/standard (요청+대화에서 요구 명확화 완료)
- [x] User Stories — SKIP (운영자 1인, 내부 자가치유 동작; 워크플로는 FR로 포착)
- [x] Workflow Planning — 단일 단순 변경, 2 유닛으로 직행
- [x] Application Design — SKIP (신규 컴포넌트 없음; 기존 함수에 필드/분기 추가)
- [x] Units Generation — SKIP (단일 변경: daemon Python stamp + launcher TS skew-check)
- [x] Construction (per-unit Code Generation)
  - [x] U-DAEMON — snapshot에 code_version 스탬프 (runtime: `_resolve_code_version` + `__init__` + publish_snapshot)
  - [x] U-LAUNCHER — daemon.ts `gitHead`/`detectCodeSkew`/`restartForStaleCode` + ensureRunning 게이트 + 6-case 테스트
- [x] Build & Test — launcher-f43 6 pass, 회귀 52 pass, 콘솔 127 pass, steering 136 pass
