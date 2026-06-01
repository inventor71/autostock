# F27 Code Generation Plan — verify-harness non-root

> Worktree: `.claude/worktrees/F27` (branch `feat/F27`, base `46c48a9`). Parent-repo only.
> 설계 근거: `construction/verify-harness/infrastructure-design/`. critic 반영 완료.
> G-1(auth)=verify-first 기본(사용자 확정). G-7(volume perm)=init-perms 1차안.

## Part 1 — 단계 (체크박스)

### 신규 `scripts/verify-run.sh` (유일 진입점)
- [x] `DOCKER_UID=$(id -u)` / `DOCKER_GID=$(id -g)` export
- [x] G-7 1차안: 본 모드 실행 전 `docker compose ... run --rm init-perms` 선행(volume chown), 실패 무시 가능하게
- [x] `exec docker compose -f docker-compose.verify.yml "$@"`
- [x] 실행권한 `chmod +x`

### `docker-compose.verify.yml`
- [x] 헤더 주석(6-13)의 raw `docker compose` 예시 → `scripts/verify-run.sh ...`로 교체
- [x] verify/attach/seed-timeline 전 서비스에 `user: "${DOCKER_UID:?run via scripts/verify-run.sh}:${DOCKER_GID:?run via scripts/verify-run.sh}"`
- [x] 전 서비스 `environment`에 `HOME: /tmp`
- [x] claude 마운트 `${HOME}/.claude:/root/.claude` → `${HOME}/.claude:/tmp/.claude` (verify=:ro, attach=:rw 유지)
- [x] `init-perms` root 서비스 추가(`user:` 없음): node_modules·attach volume 마운트 + `${DOCKER_UID}:${DOCKER_GID}` chown, entrypoint로 chown 후 종료
- [x] `PYTHONDONTWRITEBYTECODE`/`HYPOTHESIS_STORAGE_DIRECTORY`는 유지(잔여물 최소화)

### `Dockerfile.verify`
- [x] `RUN mkdir -p /tmp/.claude && chmod 777 /tmp/.claude` (HOME=/tmp 하 claude 설정 경로; bind-shadow 아님)
- [x] `USER` 지시 추가하지 않음(런타임 `user:`로 주입) — 주석으로 의도 명시
- [x] 빌드 툴체인은 root 설치 그대로

### `scripts/verify.sh`
- [x] `cleanup()` 정의(54-75) 삭제 + 상단 `trap cleanup EXIT`(76) 삭제 (원자적)
- [x] `run_attach()`: `git config --global --add safe.directory '*'`(185) 삭제
- [x] `run_attach()`: `.git` mv-aside 백업/`CONSOLE_GIT_RESTORE` 블록(187-198) 삭제
- [x] `run_attach()` EXIT/INT/TERM trap(214-217) → 데몬 kill만: `trap 'kill "$DAEMON_PID" 2>/dev/null||true; wait "$DAEMON_PID" 2>/dev/null||true' EXIT INT TERM`
- [x] preflight/run_typecheck/run_unit/run_smoke 본문은 불변(가드 유지)
- [x] 상단 주석(50-53 cleanup 설명, 22-24 git 설명) 정리 — non-root 전제로 갱신

### `scripts/worktree-setup.sh`
- [x] 출력 안내 명령(148-151)을 `scripts/verify-run.sh run --rm verify {typecheck,unit,smoke}` + `build`로 교체 (critic HIGH-2)
- [x] 관련 주석(19-22)도 verify-run.sh 기준으로

### 정합성
- [x] `bash -n scripts/verify.sh scripts/verify-run.sh scripts/worktree-setup.sh` 구문검사
- [x] `docker compose -f docker-compose.verify.yml config` (DOCKER_UID export 상태로) 파싱 OK

## Part 2 — Build & Test 가이드 산출 (사용자 실행)
실제 docker 4모드 실행은 사용자 환경(Docker+claude 로그인+TEST 계정) 필요 → Build&Test 단계에서
**실행 가능한 가이드** 제공. **G-1/G-7 검증을 최우선으로 명시**(사용자 요청).

## 비고
- prod 무영향(검증 하네스 전용). 롤백 = worktree/브랜치 폐기.
- 서브모듈 변경 없음 → 서브모듈 브랜치 불필요, parent gitlink 변동 없음.
