# Track F50 — TUI Status/타임라인 동일선 배치

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F50
- **Title**: TUI Status/타임라인 동일선 배치
- **Type**: feature
- **Status**: merge-awaiting
- **Branch**: feat/F50
- **Worktree**: .claude/worktrees/F50
- **Submodule branch**: — (monorepo, post-F35)
- **Base commit**: 469fa51
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Disabled (순수 UI 레이아웃 변경, 보안 영향 없음)
- **Property-Based Testing**: Disabled (UI 레이아웃 변경, PBT 대상 아님)

## Scope
autostock TUI에서 status 표시(queue, 작업중인 항목)와 타임라인 시간 navigation 바를 같은 줄에 배치.
현재 status가 타임라인 바 상단에 별도 줄로 표시되는 것을 동일 라인으로 이동.

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — minimal
- [x] User Stories — skip (순수 UI 레이아웃 변경)
- [x] Workflow Planning
- [x] Application Design — skip
- [x] Units Generation — skip
- [~] Construction (per-unit Code Generation)
  - [x] U1 — TUI 레이아웃 수정
- [x] Build & Test
