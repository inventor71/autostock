# Track F29 — Supervisor-mode codebase orientation (헷갈림·경로 혼선 개선)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F29
- **Title**: Supervisor 모드에서 에이전트가 코드베이스 구조를 빠르게 파악하도록 개선 — 경로·구조 혼선 감소, 첫 턴부터 정확한 파일 읽기
- **Type**: feature
- **Status**: active
- **Branch**: feat/F29 (TBD)
- **Worktree**: .claude/worktrees/F29 (TBD)
- **Submodule branch**: — (TBD, likely no submodule changes — prompt/knowledge/snapshot only)
- **Base commit**: bb2da2d
- **Start Date**: 2026-06-01T14:21:28Z

## Problem (observed in supervisor-mode runtime test, 2026-06-01)
Supervisor 모드에서 코드 읽기가 가능한 건 확인했지만, 에이전트가 헷갈려함:
- `/app/src/main.py` → File not found (Docker 컨테이너 bind-mount 내 경로 혼선)
- `/app/src/agent/prompts.py` → success (실제로 존재하는 파일)
- 결국 올바른 파일들을 찾아서 좋은 답변을 줬지만, **불필요한 시행착오**가 있었음

추정 원인:
1. Docker attach 환경에서 `AUTOSTOCK_ROOT=/app`인데, 프로젝트 구조에 대한 사전 지식 없이 경로를 추측함
2. supervisor 진입 시점에 코드베이스 레이아웃 요약이 없음 (어디서부터 봐야 할지 모름)
3. `steering/monitor.json`에는 운영 상태만 있고 코드 구조 정보는 없음

## Scope (잠정 — 요구사항 확정 전)
- supervisor 진입 시 에이전트가 프로젝트 구조(context map)를 한눈에 파악할 수 있게
- 가능한 접근: (a) `AUTOSTOCK_ROOT/`에 `CODEBUDDY.md`-스타일 프로젝트 맵 파일 제공, (b) supervisor system-prompt에 구조 요약 주입, (c) `steer_read{view:codebase_map}` MCP, (d) opencode의 `AGENTS.md`/`CLAUDE.md` 활용
- F26의 supervisor 권한 프로파일 위에서 동작 (별도 권한 변경 없음)

## ⏸️ RESUME POINT (/ai-dlc-resume)
**Paused at: 초기 생성 — 요구사항 분석 시작 전.** Resume 시:
1. supervisor 테스트에서 관찰된 혼선 패턴을 더 분석 (정확히 어떤 파일들을 시행착오 했는지)
2. 프로젝트 구조 맵을 어떤 형태로 제공할지 설계 질문 작성
3. F26(권한)·F28(UI 지식)과의 관계 확인

## Stage Progress
- [x] Workspace Detection — brownfield; RE artifacts exist
- [ ] Requirements Analysis — not started
- [ ] Workflow Planning
- [ ] Application Design
- [ ] Construction
- [ ] Build & Test
