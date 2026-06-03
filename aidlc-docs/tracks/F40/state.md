# Track F40 — autostock 런처 `-h`/`--help` 핸들러 (런처 고유 옵션 노출)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F40
- **Title**: autostock 런처 `-h`/`--help` 핸들러 — `--supervisor` 등 런처 고유 옵션 노출 + opencode 패스스루 안내
- **Type**: feature
- **Status**: merged → main 65e65ab (2026-06-03)
- **Branch**: feat/F40
- **Worktree**: .claude/worktrees/F40
- **Submodule branch**: — (monorepo, post-F35; 런처는 parent repo `operator-console/launcher/`)
- **Base commit**: 72aba01
- **Start Date**: 2026-06-03T10:02:35Z

## Extension Configuration
- **Security Baseline**: N/A — `extensions/` 디렉터리에 opt-in 룰 파일 없음(빈 디렉터리). 추가로 비밀/토큰을 다루지 않으며, 오히려 도움말은 비밀값을 출력하지 않음(BR-6 준수).
- **Property-Based Testing**: N/A — opt-in 룰 없음. 순수 문자열 출력 함수라 스냅샷/단위 테스트로 충분.

## Scope
`operator-console/launcher/cli.ts`는 현재 인자 파싱/도움말이 전혀 없다. `--supervisor`만 가로채
나머지를 opencode CLI로 무가공 전달하므로, `autostock -h`는 런처가 아니라 **opencode의 help**를
띄운다 → 런처 고유 옵션(`--supervisor`)이 어디에도 노출되지 않는다.

이 트랙은 런처에 `-h`/`--help` 핸들러를 추가해:
- autostock 고유 옵션(`--supervisor`)과 그 의미(supervisor read-only 프로파일 진입)를 설명하고,
- 그 외 인자는 opencode로 패스스루됨을 명시하고(예: `-s ses_x` 세션 재개),
- opencode 자체 help 보는 법을 안내한다.

관련: [[console-native-launcher]] (autostock 런처 구조), F26 supervisor 모드.

## Stage Progress
- [x] Workspace Detection — brownfield, monorepo post-F35, no RE re-run
- [x] Requirements Analysis — minimal; loose-fuse help 확정 (`inception/requirements/F40-launcher-help-requirements.md`)
- [ ] User Stories — skip (개발자용 CLI 도움말 텍스트, 단일 터치포인트, 모호성 없음)
- [x] Workflow Planning — minimal; Code Gen plan: `construction/plans/F40-launcher-help-code-generation-plan.md`
- [x] Application Design — skip (신규 컴포넌트/메서드 없음, 기존 cli.ts 내 순수 함수 2개 추가)
- [x] Units Generation — skip (단일 유닛)
- [x] Construction (per-unit Code Generation)
  - [x] launcher help — `cli.ts` `classifyArgs`/`launcherHelpSection`/`runHelp` + main() short-circuit; 테스트 +7
- [x] Build & Test — `bun test test/launcher.test.ts` → 45 pass / 0 fail (worktree feat/F40, uncommitted)
