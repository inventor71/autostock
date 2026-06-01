# Track F32 — Timeline Markers 사라짐 버그 수정

> Per-track state. **Single writer = this track's worktree session.**

## Track Info
- **Track ID**: F32
- **Title**: Timeline Markers 사라짐 버그 수정
- **Type**: bugfix
- **Status**: merged
- **Branch**: feat/F32
- **Worktree**: .claude/worktrees/F32
- **Submodule branch**: —
- **Base commit**: a3e67ee
- **Start Date**: 2026-06-02T00:00:00Z

## Scope
타임라인 바에서 human intervention 마커가 사라지는 버그. 틱/레이아웃은 정상.
날짜를 변경했다 돌아오면 마커가 복원됨.

**Root cause**: `_interventions_tail()`가 `human_directives.jsonl`의 마지막 150줄만
스캔. non-trade 커맨드(note/pause)가 쌓이면 trade intervention이 150줄 윈도우 밖으로
밀려나 모니터에 빈 interventions 배열이 publish됨. TUI의 historical path는 전체 파일을
읽어 ET-date로 필터링하므로 date nav 후 복원됨.

**Fix**: `_interventions_tail(path, et_date)` — ET-date 필터 추가. `publish_monitor()`가
`session_et_date`를 전달하면, 파일 끝에서부터 역방향 스캔하여 해당 날짜의 intervention만
최대 50개 수집. 레거시 라인 윈도우 경로는 하위 호환성 유지.

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — minimal
- [x] Code Generation — runtime.py + tests
- [x] Build & Test — 566 passed (19 timeline, 0 fail)
