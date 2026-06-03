# F40 — Code Generation Plan (launcher `-h`/`--help` loose-fuse)

> Worktree: `.claude/worktrees/F40` (feat/F40). 대상: `operator-console/launcher/cli.ts` (+ test).
> 요구사항: `aidlc-docs/inception/requirements/F40-launcher-help-requirements.md`.

## 구현 단계
- [x] S1. `cli.ts` — `classifyArgs(userArgs)` 순수 함수 추출(`{supervisor,help,consoleArgs}`),
      `--supervisor` strip / `-h`·`--help` 유지. export 완료.
- [x] S2. `cli.ts` — `launcherHelpSection()` 순수 함수(런처 섹션 텍스트, 비밀값 미포함). export 완료.
- [x] S3. `cli.ts` — `main()` 0번 단계에서 help short-circuit → `runHelp()`(preflight/데몬 이전,
      런처 섹션 출력 후 `bun run dev -- …` spawn, config 실패 시 exit 0).
- [x] S4. `main()` 비-help 경로 `classifyArgs` 재사용(기존 inline supervisor 로직 대체, 동작 보존).
- [x] S5. `test/launcher.test.ts` — F40 describe 2개(classifyArgs 5케이스 + launcherHelpSection 2케이스).
- [x] S6. 검증: `bun test test/launcher.test.ts` → **45 pass / 0 fail** (+7 신규). 렌더 스모크 확인.

## 비고
- opencode `.strict()`가 unknown 인자를 거부하므로 런처 측 미인식 경고 없음(요구 비목표).
- spawn 호출부는 help/비-help 공통 형태(`bun run dev -- …`)라 회귀 위험 낮음.
