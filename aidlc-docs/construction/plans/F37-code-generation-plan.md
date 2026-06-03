# F37 — Code Generation Plan: `ALPACA_SECRET_KEY` → `ALPACA_API_SECRET`

**Type**: refactor (config key rename, behavior-preserving) · **하드 리네임**(폴백 없음) · 범위 = 이 키만
**Worktree**: `.claude/worktrees/F37` (feat/F37) — 모든 코드 변경은 여기서.

## 단일 단위: `config-key-rename`

### A. Python (env 필드 + 사용처)
- [x] `config/config.py:121` — Pydantic 필드 `alpaca_secret_key` → `alpaca_api_secret`
      (`env_prefix=""` 이므로 자동으로 환경변수 `ALPACA_API_SECRET`를 읽음)
- [x] `src/data/intraday_collector.py:134` — `settings.alpaca_secret_key` → `settings.alpaca_api_secret`
- [x] `src/agent/equity_log.py:123` — `s.alpaca_secret_key` → `s.alpaca_api_secret`
- [x] `src/agent/tools/__main__.py:28` — `settings.alpaca_secret_key` → `settings.alpaca_api_secret`

### B. TypeScript (operator-console)
- [x] `operator-console/src/alpaca-data.ts` — env키·const·헤더(L72)·가드(L56/58)·401 메시지(L167) 모두 `ALPACA_API_SECRET`
- [x] `operator-console/test/alpaca-data.test.ts` — L18/L47 `process.env.ALPACA_API_SECRET`
- [x] `operator-console/cli/.opencode/opencode.jsonc:25` — **(계획 외 추가 발견)** MCP env passthrough `ALPACA_SECRET_KEY: {env:ALPACA_SECRET_KEY}` → `ALPACA_API_SECRET: {env:ALPACA_API_SECRET}` (잔존 grep으로 포착; 콘솔 MCP가 시크릿 못 받는 silent-break 방지)

### C. 문서 / 예시 파일
- [x] `.env.example:3` — `ALPACA_API_SECRET=`
- [x] `.env.test.example:8` — `ALPACA_API_SECRET=`
- [x] `README.md:32` — `export ALPACA_API_SECRET=...`
- [x] `config/settings.yaml:14` — 주석 `ALPACA_API_KEY, ALPACA_API_SECRET`

### D. 로컬 시크릿 파일 (gitignored, 값 유지)
- [x] `.env:3` (main 트리) — 키명만 `ALPACA_API_SECRET=`로 변경, 값 유지·미출력 (sed)

### 손대지 않음 (역사적 기록)
- `aidlc-docs/construction/build-and-test/intraday-redesign/*`, `aidlc-docs/tracks/F10/state.md`
- 다른 트랙 worktree(`.claude/worktrees/F30/...`)

## Build & Test
- [x] `grep ALPACA_SECRET_KEY` 잔존 0건(역사적 aidlc-docs 문서 제외; compose/verify.sh는 generic `ALPACA_*` 주석이라 dotenv 단일소스로 자동 커버)
- [x] Python smoke: `Settings()` — `alpaca_api_secret` 필드 존재 + 옛 `alpaca_secret_key` 제거 + 환경변수 `ALPACA_API_SECRET` 매핑 확인 + `py_compile` 4파일 OK
- [x] TS: `bun test test/alpaca-data.test.ts` → **24 pass / 0 fail** (env 주입 시; 모듈 import-time 가드는 기존부터 OS env 요구 — 본 변경과 무관)
