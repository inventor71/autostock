# Track F35 — CLI 서브모듈을 autostock 단일 repo로 통합 (de-submodule / monorepo)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F35
- **Title**: `operator-console/cli` 서브모듈을 autostock 본 repo로 통합 (monorepo)
- **Type**: refactor (repo 구조 변경, 동작 보존) — `/ai-dlc-request`로 진입했으나 본질은 구조 리팩토링
- **Status**: active
- **Branch**: feat/F35 (TBD)
- **Worktree**: — (구조 변경이라 worktree 격리 모델과 충돌; 아래 "실행 위치" 참고)
- **Submodule branch**: — (이 트랙은 서브모듈 자체를 제거하는 것이 목적)
- **Base commit**: 6dd91ab (main @ 트랙 생성 시점)
- **Start Date**: 2026-06-03T00:40:15Z

## Extension Configuration
- **Security Baseline**: Enabled — 통합 시 `.env`/`.gitleaksignore`/시크릿이 새 위치로 이동.
  SECURITY-03(로그 시크릿 금지)/시크릿 파일 .gitignore 유지가 적용 대상.
- **Property-Based Testing**: TBD (Requirements에서 결정)

## Scope
현재 TUI 콘솔(`operator-console/cli`)은 별도 GitHub repo `inventor71/autostock-cli`
(opencode 포크)로 분리된 git 서브모듈이다. 테스트/검증 시 git 컨텍스트가 분리되어
worktree에 서브모듈 working tree가 자동 포함되지 않고, 트랙마다 서브모듈 브랜치를 따로 따고
머지 시점에 부모 gitlink를 커밋해야 하는 반복 비용이 있다 (F4/F8/F13/F19/F31/F34에서 반복).
이 트랙은 서브모듈을 본 repo로 흡수해 단일 git 컨텍스트로 만든다.

관련 메모: [[submodule-merge-workflow]] (이 워크플로를 없애는 것이 목적),
[[aidlc-multitrack-partition]] (worktree 게이트가 서브모듈을 별도 처리), [[console-native-launcher]].

## 핵심 사실 (조사 결과)
- 서브모듈 = opencode 포크, 별도 repo `git@github.com:inventor71/autostock-cli.git`, branch=main.
- 포크 히스토리는 squash 임포트로 **43 커밋** (.git/modules ≈ 56M) — 상류 opencode 전체
  히스토리는 없음. → 히스토리 보존 subtree 머지가 현실적.
- working tree ≈ 101M (README 다국어/assets/.opencode/.hypothesis 포함; node_modules는 gitignore).
- 서브모듈 참조 위치: `docker-compose.verify.yml`, `scripts/worktree-setup.sh`,
  `scripts/verify.sh`, `scripts/verify-run.sh`, `src/agent/steering/runtime.py`,
  AI-DLC 룰(`concurrent-tracks.md`, `code-generation.md`), `CLAUDE.md`, `.gitmodules`.

## 실행 위치 주의 (worktree 게이트 예외)
서브모듈 제거는 `.gitmodules`/gitlink/repo 루트 트리를 바꾸는 **repo 구조 변경**이라
일반 worktree 격리(서브모듈 전제) 모델에 들어맞지 않는다. 전용 브랜치(feat/F35)에서
수행하되 worktree 격리 방식은 Requirements/Plan에서 확정한다.

## Stage Progress
- [x] Workspace Detection — brownfield, 기존 트랙 다수 active(아래 주의). 새 요청으로 진행.
- [ ] Requirements Analysis — standard (구조 결정 + 명확화 질문)
- [ ] User Stories — skip 예정 (사용자 대면 기능 아님; 개발자/AI 워크플로 개선)
- [ ] Workflow Planning
- [ ] Application Design — skip 예정 (새 컴포넌트 없음)
- [ ] Units Generation — skip 예정 (단일 작업)
- [ ] Construction (repo 구조 변경 + 툴링/룰 갱신)
- [ ] Build & Test (통합 후 verify 하네스가 단일 컨텍스트에서 동작 확인)

## 활성 트랙 주의 (Workspace Detection)
레지스트리에 active 트랙 다수: F6, R1, M1, F16, F28, F30, F33(paused). F35는 이들의
서브모듈 브랜치/gitlink 작업과 충돌할 수 있으므로, 통합 시점에 미머지 서브모듈 브랜치
(feat/F22, feat/F25, feat/console-native-launcher 등 로컬, origin feat/F26 등) 처리 방침을 정해야 함.
