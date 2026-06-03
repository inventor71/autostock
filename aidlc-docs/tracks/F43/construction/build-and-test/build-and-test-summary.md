# F43 Build & Test 요약 — 데몬 코드 버전 스큐 자가치유

## 변경 파일
- `src/agent/steering/runtime.py` — `_resolve_code_version()` 헬퍼 + `__init__`의 `self._code_version`
  + snapshot dict에 `code_version` 필드(U-DAEMON, FR-1/AC-1).
- `operator-console/launcher/daemon.ts` — `gitHead()`, `detectCodeSkew()`, `restartForStaleCode()`
  + `ensureRunning()`의 fresh-attach 분기에 스큐 게이트(U-LAUNCHER, FR-2~5/G-1/G-2).
- `operator-console/test/launcher-f43.test.ts` — 6 케이스(신규).
- `tests/test_steering_runtime.py` — snapshot `code_version` 존재 단언 추가(AC-1).

## 빌드
- 런처/콘솔은 Bun 런타임 직접 실행(별도 컴파일 단계 없음). Python은 인터프리티드.
- 표준 typecheck(tsgo)는 `operator-console/cli` 대상이며 launcher/는 자체 tsconfig 없음(기존과 동일).
  standalone tsc 검사 결과 신규 코드에 실제 타입 오류 없음(잔여 진단은 @types/node·bun 미주입 아티팩트).

## 테스트 결과 (모두 그린)
- `bun test test/launcher-f43.test.ts` → **6 pass / 0 fail** (AC-2~5 + 루프방지 + 실패-시-throw).
- 런처 회귀 `launcher.test.ts` + `launcher-f14.test.ts` → **52 pass**.
- 비-키게이트 콘솔 스위트 8파일 → **127 pass / 0 fail**.
- Python steering 스위트(`-k steer/runtime/snapshot/channel`) → **136 pass**.
- `test_steering_runtime.py`(신규 단언 포함) → **9 pass**.
- Python 단위 점검: `_resolve_code_version`가 실제 repo HEAD 일치, 비-git/없는경로 → `""`(무예외).

## 알려진 한계 / 범위 밖
- 전체 `bun test` 스위트는 `alpaca-data.test.ts`가 `ALPACA_API_*` 키를 요구해 키 없이 중단됨
  — **기존 조건**(F43 변경과 무관, verify 하네스는 TEST 키로 docker 내 실행).
- systemd 밖 수동 실행 데몬은 `systemctl restart`가 별도 인스턴스를 기동하므로 본 트랙 범위 밖.
- 채널 파싱-실패 무한로그/사일런트-노옵 수정은 별도 트랙(사용자 결정).

## 상태
- Build & Test PASS → 트랙 `merge-awaiting`. `/ai-dlc-merge` 로 머지.
