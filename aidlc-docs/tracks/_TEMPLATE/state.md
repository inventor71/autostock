# Track <ID> — <Title>

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: <Fn>
- **Title**: <one line>
- **Type**: feature | refactor | deprecate
- **Status**: active
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
