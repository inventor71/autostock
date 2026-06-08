# Track F71 — autostock 모바일(안드로이드) 앱 — 경로 A (Tailscale + opencode serve + PWA)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F71
- **Title**: 폰에서 autostock operator 콘솔 — Tailscale + `opencode serve` + PWA(packages/app) + 데몬 read 표면
- **Type**: feature
- **Status**: backlog  <!-- 등록만. Q&A로 스코프 확정 후 사용자가 /ai-dlc-resume으로 진행 -->
- **Branch**: feat/F71 (TBD)
- **Worktree**: .claude/worktrees/F71 (TBD)
- **Submodule branch**: — (TBD — operator-console/cli 건드릴 가능성 높음: serve 진입점/PWA)
- **Base commit**: TBD (resume 시점 main)
- **Start Date**: TBD

## Extension Configuration
- **Security Baseline**: TBD (Applicable 예상 — 트레이딩 제어를 네트워크 노출: 서버 비번/tailnet/권한 프로파일/주문 confirm 게이트)
- **Property-Based Testing**: TBD (제한적 — UI/통합 위주, 순수 로직 적으면 N/A 가능)

## Scope (조사 기반, Q&A로 확정 예정)
경로 A MVP: PC(데몬 호스트)에서 `opencode serve`를 MCP/STEERING wiring과 함께 띄우고, 폰이
**Tailscale**로 그 서버에 도달해 **PWA(`packages/app`)** 로 autostock operator 콘솔을 사용.
모바일 경험 = **대화형 operator**(steer_read 읽기 + steer/주문 도구), opentui 비주얼 대시보드는
범위 밖(후속). 필수 변경: serve 진입점 + 권한 안전기본값 + 시크릿 위생.

상세 조사: `aidlc-docs/research/mobile-app-investigation.md` (어떤 앱/연결/Claude RC 대비/필수 변경).

> **상태: 등록만 됨(backlog).** 사용자 Q&A 진행 → 스코프 확정 후 레지스트리/이 파일 업데이트 →
> 사용자가 `/ai-dlc-resume F71`로 inception 시작 예정.

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. `/ai-dlc-merge`가 큐 구성·충돌 해결 시 참조.
> 비워두면 `/ai-dlc-merge`가 `git diff --name-only`로 자동 추론.

- **공유 파일 (주의)**: <다른 활성 트랙과 겹칠 가능성 높은 파일 — 예: `src/agent/steering/runtime.py`>
- **API/시그니처 변경**: <rename, 삭제, 함수 분할 — 다른 트랙 rebase 시 수동 조정 필요한 부분>
- **알려진 동시 변경**: <같은 파일을 건드리는 게 확실한 다른 트랙 ID (예: F44)>

## Stage Progress
- [ ] Workspace Detection
- [ ] Requirements Analysis — <depth>
- [ ] User Stories — <execute/skip + reason>
- [ ] Workflow Planning
- [ ] Application Design — <execute/skip>
- [ ] Units Generation — <execute/skip>
- [ ] Construction (per-unit Code Generation)
  - [ ] <Unit> — <note>
- [ ] Build & Test
