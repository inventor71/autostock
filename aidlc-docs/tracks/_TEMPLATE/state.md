# Track <ID> — <Title>

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: <Fn>
- **Title**: <one line>
- **Type**: feature | refactor | deprecate
- **Status**: active  <!-- active → merge-awaiting (set when Build & Test passes) → merged (by /ai-dlc-merge) -->
- **Branch**: feat/<track>
- **Worktree**: .claude/worktrees/<track>
- **Submodule branch**: — (or feat/<track> if operator-console/cli is touched)
- **Base commit**: <parent sha at branch creation>
- **Start Date**: <ISO 8601>

## Extension Configuration
- **Security Baseline**: <Enabled/Disabled — applicable rules + N/A rationale>
- **Property-Based Testing**: <Enabled/Disabled — mode + framework>

## Scope
<what this track will build/change; link related memories with [[name]] if useful>

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
