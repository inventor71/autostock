# F72 — Code Generation Plan (unit "screening")

**Base**: functional-design.md (승인 2026-06-11) · worktree `feat/F72`

## Part 2 실행 체크리스트

### A. Python — 캡처
- [x] A1. `src/agent/screening_log.py` 신규 — `scan_path`/`verdicts_path`/`record_scan`(원자적, fail-honest)/`read_scan`/`read_verdicts`(관대 파싱)
- [x] A2. `src/agent/tools/__main__.py` scoreboard 분기에 `record_scan` 훅 (AGENT_JOURNAL_ROOT or Journal().root)
- [x] A3. `src/agent/prompts.py` — morning research Discovery에 verdict 의무 문구; F23 병렬 research discovery 프롬프트 확인 후 동일 적용
- [x] A4. `tests/` — screening_log 단위 + hypothesis round-trip PBT + fail-honest + 프롬프트 문구 단언

### B. TypeScript — 콘솔 조회
- [x] B1. `operator-console/src/parser.ts` — READ_VERBS에 `screening`
- [x] B2. `operator-console/src/filedrop.ts` — screeningDir + `listScreeningDates` + `readScreening`
- [x] B3. `operator-console/src/steer-handler.ts` — `/screening [date]` 디스패치: 날짜 regex 검증 → 최신/지정 날짜 read → 포맷 출력 / no-data 문자열
- [x] B4. `operator-console/test/` — 파서·날짜 검증(주입 거부)·최신 선택·no-data·포맷 테스트

### C. 검증
- [x] C1. Python 테스트 (pytest 해당 모듈) 통과
- [x] C2. 콘솔 테스트 (bun test) + typecheck 통과
- [x] C3. 수동 smoke: scoreboard 1회 실행 → scan.json 생성 확인 → 콘솔 핸들러로 조회
