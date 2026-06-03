# Track F37 — `.env` 키 네이밍 정합화: `ALPACA_SECRET_KEY` → `ALPACA_API_SECRET`

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F37
- **Title**: `.env` 키 네이밍 컨벤션 정합화 — `ALPACA_SECRET_KEY` → `ALPACA_API_SECRET`
- **Type**: refactor (config key rename; behavior-preserving)
- **Status**: merged (→ main f26ab6a, code commit fd5cd5b)
- **Branch**: feat/F37
- **Worktree**: .claude/worktrees/F37
- **Submodule branch**: N/A — monorepo (post-F35); operator-console는 in-repo 디렉터리
- **Base commit**: 1553dc0 (main)
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Enabled — 시크릿 키 **이름**만 변경(값/저장방식 불변). SECRET-* 규칙 대부분 N/A; 단 로컬 `.env`(실제 시크릿 보유, gitignored) 편집 시 값 노출/로깅 금지.
- **Property-Based Testing**: N/A (단순 rename; 기존 단위 테스트로 충분).

## Scope
`.env` 키 이름 컨벤션이 불일치: Alpaca만 `ALPACA_API_KEY` + `ALPACA_SECRET_KEY`로
`<provider>_..._KEY`/`<provider>_..._SECRET` 패턴에서 벗어남
(cf. `BROKER_API_KEY`/`BROKER_API_SECRET`, `KIS_PAPER_APP_KEY`/`KIS_PAPER_APP_SECRET`).
→ `ALPACA_SECRET_KEY` 를 `ALPACA_API_SECRET` 으로 통일.

참조 지점(초기 조사):
- Python: `config/config.py:121` (Pydantic 필드 `alpaca_secret_key`), 사용처
  `src/data/intraday_collector.py:134`, `src/agent/equity_log.py:123`,
  `src/agent/tools/__main__.py:28`
- TS: `operator-console/src/alpaca-data.ts` (54/56/58/72/167), 테스트 `test/alpaca-data.test.ts`
- 문서/예시: `.env.example`, `.env.test.example`, `README.md:32`, `config/settings.yaml:14`
- 로컬(gitignored) `.env:3` — 실제 시크릿 보유 (앱 동작 유지 위해 키명 갱신 필요)

[[feedback-monorepo-refactor-as-native]] — rename은 "항상 그랬던 것처럼" 깔끔히, 마이그레이션 강조 주석 금지.

## Stage Progress
- [x] Workspace Detection — brownfield, RE 아티팩트 존재 → RE skip
- [x] Requirements Analysis — minimal. 결정: ① 하드 리네임(폴백 없음, 옛 키 완전 제거) ② 범위 = `ALPACA_SECRET_KEY`만 ③ 로컬 `.env` 키명 갱신(값 유지)
- [ ] User Stories — skip (내부 config rename, 사용자 워크플로 영향 없음)
- [ ] Workflow Planning
- [ ] Application Design — skip (신규 컴포넌트/메서드 없음)
- [ ] Units Generation — skip (단일 단위)
- [x] Construction (Code Generation) — single unit `config-key-rename` 완료
  - Python 4 + TS 2 + opencode.jsonc(계획 외 발견) + docs 4 + 로컬 .env 키명
- [x] Build & Test — Python smoke + py_compile OK; `bun test alpaca-data` 24 pass/0 fail; 잔존 grep 0건(역사적 문서 제외)

## 발견/주의
- **계획 외 1건**: `operator-console/cli/.opencode/opencode.jsonc`의 MCP env passthrough가
  옛 키를 `{env:ALPACA_SECRET_KEY}`로 주입 중 → 같이 변경(미변경 시 콘솔 MCP가 시크릿 못 받는 silent-break). cf. [[f4-steering-runtime-wiring]]
- 역사적 aidlc-docs(F10 state, intraday build-instructions/summary)는 의도적으로 미변경.
- 로컬 `.env`는 **main 트리**에서 갱신(worktree엔 .env 없음, 앱은 main에서 구동). cf. [[worktree-live-verification]]
