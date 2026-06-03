# F43 코드 생성 계획 — 데몬 코드 버전 스큐 자가치유

## U-DAEMON — 데몬이 코드 버전을 snapshot에 스탬프
- [x] D1. `runtime.py`: 모듈 헬퍼 `_resolve_code_version(root) -> str` 추가
      (`git rev-parse HEAD`, cwd=root, 실패/예외 → `""`, 절대 raise 안 함, timeout=5s).
- [x] D2. `SteeringRuntime.__init__`: `self._code_version = _resolve_code_version(_REPO_ROOT)`
      (기동 1회 — 인메모리 코드 버전 고정; 이후 머지 영향 없음). FR-1.
- [x] D3. `publish_snapshot`의 snapshot dict에 `"code_version": self._code_version` 추가.
      → `channel.publish_snapshot`가 `published_at`과 함께 `steering/snapshot.json`에 기록. AC-1.

## U-LAUNCHER — autostock이 스큐 감지 후 재시작
- [x] L1. `daemon.ts`: `gitHead()` — `git -C <autostockRoot> rev-parse HEAD` (injected `run`).
      code≠0 → `""` (G-1 fail-open).
- [x] L2. `detectCodeSkew()` — snapshot의 `code_version`과 `gitHead()` 비교:
      - 런처 HEAD `""`(미상) → `{stale:false}` (G-1, 재시작 안 함).
      - snapshot에 `code_version` **키 부재**(pre-F43 구데몬) → `{stale:true}` (FR-4, 1회 업그레이드).
      - 키 존재 but 값 `""`(F43 데몬, git 미해결) → `{stale:false}` (루프 방지 — 비교 불가시 fail-open).
      - 값 존재 & ≠ HEAD → `{stale:true}` (FR-2). 같으면 `{stale:false}`.
- [x] L3. `restartForStaleCode(reason)` — `systemctl restart` 1회 + `healthWait(RESTART_HEALTH_MS)`;
      실패 시 `DaemonStartError`. reason을 `HealthResult.reason`에 표기. FR-3/FR-5/G-2.
- [x] L4. `ensureRunning()`의 `isFreshNow()→attach` 분기에 스큐 게이트 삽입:
      stale면 `restartForStaleCode` 반환, 아니면 기존 probeAdvance attach. FR-2.

## 테스트
- [x] T1. `operator-console/test/launcher-f43.test.ts` — F14 하네스 패턴 재사용:
      - 동일 SHA → 재시작 0회, attach. (AC-3)
      - 다른 SHA → 재시작 1회, healthy. (AC-2)
      - `code_version` 키 부재 → 재시작 1회. (AC-4)
      - 런처 HEAD `""`(git 실패) → 재시작 0회, attach. (AC-5, G-1)
      - 키 존재 값 `""` → 재시작 0회 (루프 방지).
      - restart 후에도 snapshot 정지 → `DaemonStartError`. (G-2)
- [x] T2. Python: `_resolve_code_version`가 비-git 경로에서 `""` 반환(예외 없음) 단위 확인.

## Build & Test
- [x] B1. `bun test` (operator-console) 그린.
- [x] B2. Python typecheck/unit (steering) 영향 없음 확인.
- [x] B3. state.md 진행 갱신 + merge-awaiting.
