# F27 Code Summary — verify-harness non-root

> Worktree `.claude/worktrees/F27` (branch `feat/F27`, base `46c48a9`). Parent-repo only, 서브모듈 변경 없음.
> 변경: 5 files 수정(Dockerfile.verify / docker-compose.verify.yml / verify.sh / worktree-setup.sh) + 신규 `scripts/verify-run.sh`.
> 오프라인 모드(build/typecheck/unit) + 호스트소유/sudo-free **직접 실행 검증 통과**(아래). smoke/attach는 사용자 실행.

## 변경 내용

### 신규 `scripts/verify-run.sh` (유일 진입점)
- `DOCKER_UID=$(id -u)` / `DOCKER_GID=$(id -g)` export 후 `docker compose -f docker-compose.verify.yml "$@"`.
- `run`/`up` 서브커맨드일 때만 `init-perms`(root volume chown)를 선행 호출, 실패 시 경고만.
- `cd "$(dirname "$0")/.."`로 worktree 루트에서 실행 보장.
- **(Build&Test 발견) named-volume 마운트포인트 호스트소유 선생성** — docker 데몬(root)이
  `operator-console/{,cli/}node_modules`·`steering`/`workspace`/`logs`를 worktree에 root:root로
  만드는 잔여 제거(빈 dir+부모 호스트소유라 제거 자체는 sudo 불필요했지만, "root 소유 완전 제거"
  의도 충족). `mkdir -p`로 docker가 호스트소유 dir를 재사용하게 함.

### `docker-compose.verify.yml`
- 헤더 주석을 `verify-run.sh` 호출로 교체.
- `verify`/`attach`/`seed-timeline`에 `user: "${DOCKER_UID:?run via scripts/verify-run.sh}:${DOCKER_GID:?...}"` (fail-loud).
- 전 서비스 `environment`에 `HOME: /tmp`.
- claude 마운트 `${HOME}/.claude:/root/.claude` → `${HOME}/.claude:/tmp/.claude` (verify=:ro, attach=:rw).
- 신규 `init-perms` 서비스(유일하게 `user:` 없음=root): 볼륨을 `/v/*`에 마운트하고 `chown $DOCKER_UID:$DOCKER_GID` 후 종료 (G-7, bind-shadow 회피).

### `Dockerfile.verify`
- `RUN mkdir -p /tmp/.claude && chmod 1777 /tmp` + `USER` 미추가(런타임 `user:` 주입) 의도 주석.
- **(Build&Test 발견) `npm install -g node-gyp`** 추가 — npm은 node-gyp를 내부 번들만 두고 PATH에
  노출 안 함. bun의 tree-sitter 네이티브 애드온 rebuild가 PATH의 `node-gyp`를 spawn → fresh
  install이 `spawn node-gyp ENOENT`로 실패하던 잠복 버그(root에서도 발생). `node-gyp --version`을
  빌드 단계 검증으로 추가. (build-essential은 이미 있었음 — node-gyp 본체만 누락)

### `scripts/verify.sh` (net −34행)
- `cleanup()` 함수 + 상단 `trap cleanup EXIT` **삭제** (F17 chown handback 소멸).
- `run_attach()`의 `safe.directory '*'` + `.git` mv-aside 백업/복원 블록 **삭제**, 근거 주석 교정(gitdir-escape는 경로문제·non-root 무관, `[-f]` 가드 지혜 보존 명시, `rm .git` 금지).
- attach trap을 데몬 kill만으로 축소(원자적).
- preflight/typecheck/unit/smoke 본문 불변.

### `scripts/worktree-setup.sh`
- 출력 안내 명령 + `--docker-verify` 헤더 주석을 `verify-run.sh`로 교체.

## 실행 검증 (이 세션, uid 1000:989 — PASS)
- `bash -n` ×3 + `docker compose config` 파싱 OK; DOCKER_UID 미설정 시 fail-loud 확인.
- `verify-run.sh build` OK (node-gyp 베이킹 포함, `node-gyp --version` 빌드검증 통과).
- **typecheck**: init-perms→비-root `bun install`(node-gyp 네이티브 빌드)→tsgo **19/19 OK** = **⭐G-7 PASS**.
- **unit**: pytest **556 passed** (offline).
- **호스트소유**: 실행 후 `find . -xdev -user root` **공백**; root-소유 빈 마운트포인트 `rm -rf` **sudo-free** 실증.

## 미검증 (사용자 실행 — real키/claude auth 필요, 자동실행 부적절)
- **⭐G-1**: attach 실 LLM 턴이 `~/.claude.json` 미마운트로도 인증되는지 (verify-first; 실패 시 마운트 한 줄 추가).
- **⭐MEDIUM-4**: attach opencode TUI가 in-container 서브모듈 git을 호출하는지.
- **smoke**: real claude `--version` + read-only Alpaca(TEST 계정 account_number 핀).
- 최종 `git worktree remove` sudo-free(트랙 종료 시).
