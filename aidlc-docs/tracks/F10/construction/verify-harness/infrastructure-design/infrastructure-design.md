# F27 Infrastructure Design — verify-harness non-root 실행

> Unit: `verify-harness`. 검증 컨테이너를 호스트 UID:GID로 실행하고, root-소유 사후 수습
> 우회 코드를 제거한다. prod 배포 없음 — 대상은 로컬 docker-compose 검증 하네스뿐.

## 1. 확정된 설계 결정 (D-1 ~ D-3)

### D-1 — UID 주입 = 래퍼 스크립트 (승인 2026-06-01)
- 신규 `scripts/verify-run.sh`가 `id`로 호스트 UID/GID를 계산해 **export 후** compose 호출:
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  export DOCKER_UID="$(id -u)" DOCKER_GID="$(id -g)"
  exec docker compose -f docker-compose.verify.yml "$@"
  ```
- compose의 모든 서비스에 **fail-loud** 보간: `user: "${DOCKER_UID:?run via scripts/verify-run.sh}:${DOCKER_GID:?run via scripts/verify-run.sh}"`.
  - **`:-1000` 기본값 기각** (critic HIGH-2): 기본값을 두면 래퍼를 우회한 직접 `docker compose` 호출이
    UID 1000으로 조용히 떨어지고, 호스트 UID≠1000이면 (a) bind-mount 산출물이 다시 다른 소유로
    생기고 (b) `~/.claude`(0600)를 못 읽어 **인증이 조용히 실패**한다. `:?`는 변수 미설정 시
    compose가 **명확한 메시지로 즉시 실패** → 래퍼가 유일 진입점임을 강제.
- **왜 래퍼인가** (대안 기각 근거):
  - bash `$UID`는 readonly + 비-export → compose 보간이 직접 못 읽음(G-6).
  - 프로젝트 루트 `.env`(UID/GID) 방식은 그 파일이 `/app/.env`로 bind-mount되어
    **verify.sh preflight의 prod-안전 가드(`[ -e /app/.env ]` → fail)** 와 충돌 → 사용 불가.
  - 변수명을 `DOCKER_UID/DOCKER_GID`로 쓰는 이유: `UID`는 readonly라 `UID=$(id -u)` 대입 자체가 에러.
- **호출법 변경 = 필수 코드 변경** (critic HIGH-2, "문서 작업"이 아님):
  - `scripts/worktree-setup.sh:148-151` — 출력하는 안내 명령을 `docker compose -f
    docker-compose.verify.yml run --rm verify typecheck` → `scripts/verify-run.sh run --rm verify
    typecheck` 형태로 교체. **이 줄을 안 고치면 사용자가 래퍼를 우회**해 위 fail-loud에 걸린다.
  - `docker-compose.verify.yml:6-13` 헤더 주석의 raw `docker compose` 예시도 동일 교체.

### D-2 — named volume = 구조 유지, 우회 코드만 제거 (승인 2026-06-01)
- **유지**: `verify-node-modules`, `mcp-node-modules` — 목적이 root-소유 회피가 **아니라**
  host/container arch-clash 방지(bun 네이티브 애드온) + install 캐시. non-root여도 그대로 필요.
- **유지**: `attach-steering`, `attach-workspace`, `attach-logs` — 데몬 런타임 산출물을
  워크트리 밖으로 격리(오염 방지). non-root여도 격리 가치 유지.
- **제거 대상은 볼륨이 아니라 verify.sh/compose의 사후 수습 코드** (§3).

### D-3 — HOME = `/tmp` (설계자 확정)
- `user:`로 임의의 호스트 UID를 주면 이미지에 그 UID의 passwd 엔트리가 없어 `HOME`이 `/`로
  떨어지고 `~`가 쓰기 불가 → claude/bun이 설정·캐시 기록에 실패(G-1, G-2).
- compose `environment`에 `HOME=/tmp` 명시(`/tmp`는 sticky·world-writable → 모든 UID 쓰기 가능).
- claude 설정 마운트 타깃을 `/root/.claude` → **`/tmp/.claude`** 로 변경
  (`${HOME}/.claude:/tmp/.claude`). smoke=`:ro`, attach=`:rw` 유지.

> **⚠️ critic HIGH-1 — claude 인증 파일 분리 (G-1 "해결" 단정 철회).** claude CLI는 상태를 두
> 곳에 나눠 둔다: `~/.claude/.credentials.json`(마운트되는 디렉터리 **안** — OK)과
> **`~/.claude.json`**(HOME **루트**, 55KB, `oauthAccount`/`hasCompletedOnboarding` 포함 — auth
> 게이트). 현재 compose는 `~/.claude` 디렉터리만 마운트하므로 **`~/.claude.json`은 마운트되지
> 않는다**(`docker-compose.verify.yml:26,67`). HOME=/tmp면 claude는 `/tmp/.claude.json`을 찾고
> 없으면 빈 파일을 새로 만든다 → attach의 실제 LLM 턴이 onboarding/"not logged in"으로 실패할 수 있다.
>
> **단, 이는 F27이 만든 회귀가 아니다.** 현재 root 설정(HOME=/root, `/root/.claude.json` 역시
> 미마운트)도 똑같다 — F27은 HOME과 마운트 타깃을 옮길 뿐 *어떤 파일을 마운트하는지*는 안 바꾼다.
> daemon은 `subprocess.run(... )`을 `env=` 없이 호출(`src/strategy/llm/client.py:216`, HOME 상속)
> + `--no-session-persistence`(client.py:210)라 쓰기는 적지만 startup auth 읽기는 그대로다.
> 따라서 **G-1은 "해결"이 아니라 "현 root 설정과 동일 — 미해결 PRE-EXISTING 조건"**. Build&Test에서
> attach 실 LLM 턴이 인증되는지 **반드시 실측**. 실패하면 즉시 적용할 픽스(설계 §2 G-1 행 참조):
> `~/.claude.json`도 마운트하거나 `CLAUDE_CONFIG_DIR=/tmp/.claude`를 세팅(이미지 CLI 버전이
> 지원하는지 확인). **마운트 추가 시 :rw는 호스트 실 claude 설정을 컨테이너가 오염시킬 위험**이
> 있으므로 ro/copy-to-tmp 여부는 별도 결정(아래 "미해결 결정" 참조).
- bun 캐시(`~/.bun` 등)도 HOME=/tmp 하에서 `/tmp/.bun`으로 떨어져 쓰기 가능.

## 2. non-root 권한 함정 해결 (G-1 ~ G-6) — 핵심 검증 포인트

| ID | 함정 | 설계 해결 | Build&Test 실측 |
|----|------|-----------|-----------------|
| G-1 | `/root/.claude` 마운트, non-root는 `/root` 접근 불가 + **`~/.claude.json` 미마운트(auth)** | HOME=/tmp + 마운트 타깃 `/tmp/.claude` (D-3). auth 파일 분리는 **미해결 PRE-EXISTING**(D-3 경고) | **attach 실 LLM 턴 인증 성공** 실측. 실패 시 `~/.claude.json` 마운트 or `CLAUDE_CONFIG_DIR` |
| G-2 | bun/npm 캐시가 HOME에 씀, HOME 미설정 시 실패 | HOME=/tmp | `bun install --frozen-lockfile` 성공 |
| G-3 | `__pycache__`가 /app(워크트리)에 씀 | 호스트 UID 실행 → 호스트 소유라 무해. `PYTHONDONTWRITEBYTECODE=1`는 잔여물 최소화로 **유지** | pytest 후 `git worktree remove` sudo 불필요 |
| G-4 | `/app/.env`·logs·steering 쓰기 | 호스트 UID → 호스트 소유 OK. (`.env`는 gitignore, attach가 .env.test→.env 복사) | attach가 .env 생성·daemon 기동 |
| G-5 | in-container git commit이 user.name 미설정으로 실패 | non-root + 호스트 .git이면 dubious-ownership 안 뜸 → **우회 자체 제거**(§3), 해당 없음 | attach에서 git 우회 코드 부재 확인 |
| G-6 | `$UID` compose 미인식 | 래퍼가 `DOCKER_UID/DOCKER_GID` export (D-1) | verify-run.sh로 4모드 기동 |

### ⚠️ 추가 발견 — named-volume 소유권 함정 (G-7, 신규)
non-root 실행 시 **빈 named volume의 마운트포인트는 root:root로 생성**되어 non-root가
`bun install`을 그 안에 쓰지 못한다(verify-node-modules/mcp-node-modules → EACCES,
verify.sh:84/201/206에서 typecheck·attach 둘 다 첫 install에서 실패).

> **critic HIGH-3 — chmod-777-in-image은 1차안으로 부적절(우선순위 역전 교정).** node_modules
> 볼륨 타깃은 **`/app` bind-mount 하위 경로**다(`docker-compose.verify.yml:21,64`의 `.:/app`).
> Dockerfile `RUN ... chmod 777 /app/...`은 *이미지 레이어*의 `/app`에 쓰지만, 런타임에 `/app`
> 전체가 호스트 bind로 교체되어 **이미지에 구운 디렉터리/권한이 가려진다**. Docker가 빈 named
> volume을 이미지에서 seed하는 동작은 마운트포인트가 다른 마운트(/app bind) 아래 있으면
> 신뢰할 수 없고, 빈 볼륨의 소유권은 부모 dir 모드와 무관히 root:root다. 즉 chmod-777 레버는
> 안 먹을 공산이 크다.

- **1차안 (PRIMARY) = root 일회성 init이 볼륨 chown** (critic 권고로 승격): compose에
  `init-perms` 서비스(이 서비스만 `user:` 없이 root)가 named volume 마운트포인트를
  `chown $DOCKER_UID:$DOCKER_GID` 후 종료. verify-run.sh가 본 모드 전에 `run --rm init-perms`를
  먼저 호출하거나, compose `depends_on`/래퍼 시퀀싱으로 보장. 컨테이너 본체는 계속 non-root.
  → 결정적(deterministic), bind-shadow에 영향 안 받음.
- **2차안 (대안)**: Dockerfile에서 타깃 dir `mkdir -p && chmod 777` (이미지 권한 상속에 기댐) —
  **Build&Test에서 실제로 먹히는지 먼저 실측**되면 init 서비스 없이 더 단순. 단 위 HIGH-3 우려로
  기본 채택하지 않음.
- /tmp/.claude는 bind-shadow 대상이 아니라 chmod로 충분(HOME=/tmp는 1777).
- **Build&Test 최우선 검증 항목**: 첫 non-root `bun install`이 쓰기 성공하는지 — 이 트랙
  전체의 make-or-break.

## 3. 제거할 우회 코드 (FR-2)

| 파일 | 제거/변경 | 이유 |
|------|-----------|------|
| `scripts/verify.sh` `cleanup()` | `find /app -xdev -exec chown $host_owner`(F17 handback) **전체 삭제**. .turbo/node_modules/tsbuildinfo/__pycache__/.pytest_cache/.hypothesis rm 스윕 삭제 | 호스트 UID 실행 → 산출물이 처음부터 호스트 소유. 단 trap은 attach 데몬 종료용으로 일부 잔존(아래) |
| `scripts/verify.sh` `run_attach()` | `git config --global --add safe.directory '*'` 삭제. `.git` mv-aside 백업·복원(`CONSOLE_GIT_RESTORE`, verify.sh:187-198) **삭제** — 단 **근거는 아래 교정** | safe.directory: non-root+호스트소유 → dubious-ownership 미발생(맞음). mv-aside: **attach 데몬 경로가 in-container 서브모듈 git을 안 쓰기 때문**(실측 전제) |
| `scripts/verify.sh` trap+cleanup (원자적 1회 변경) | `cleanup()` 정의(54-75)와 상단 `trap cleanup EXIT`(76)를 **함께** 삭제. attach trap(214-217)을 데몬 종료만 남겨 통째 교체: `trap 'kill "$DAEMON_PID" 2>/dev/null||true; wait "$DAEMON_PID" 2>/dev/null||true' EXIT INT TERM` | critic MEDIUM-5: 함수만 지우고 trap 문자열에 `cleanup` 잔존 시 매 종료마다 "command not found". 두 변경은 lockstep 필수 |
| `docker-compose.verify.yml` | 모든 서비스에 `user: "${DOCKER_UID:?...}:${DOCKER_GID:?...}"`(fail-loud) + `HOME=/tmp` 추가, claude 마운트 `/root/.claude`→`/tmp/.claude`. 헤더 주석(6-13) raw `docker compose` 예시 → `verify-run.sh`로. `PYTHONDONTWRITEBYTECODE=1`/`HYPOTHESIS_STORAGE_DIRECTORY=/tmp/...`는 잔여물 최소화 목적 **유지** | D-1/D-3 적용 |
| `docker-compose.verify.yml` (G-7) | (1차안) root `init-perms` 서비스 추가 — named volume chown | §2 G-7 PRIMARY |
| `scripts/verify-run.sh` (신규) | UID/GID export + (G-7 1차안 시) init-perms 선행 호출 래퍼 | D-1 |
| `scripts/worktree-setup.sh:148-151` | 출력 안내 명령을 `verify-run.sh ...`로 교체 | critic HIGH-2, 래퍼 우회 방지(필수) |
| `Dockerfile.verify` | /tmp/.claude `mkdir -p && chmod 777`(bind-shadow 아님→OK). 볼륨 타깃 chmod는 2차안 시에만. `USER` 없음(런타임 `user:` 주입) | 빌드 툴체인 root 설치 유지, 실행만 non-root |

> **주의 — git 우회 제거의 *교정된* 근거 (critic MEDIUM-4)**: verify.sh:172-198은 **두 개의 별개
> 문제**를 다룬다 — (1) dubious-ownership(root가 호스트소유 repo 거부): non-root+UID 일치로 해결,
> (2) 서브모듈 `.git`이 **gitdir: 포인터 파일**로 /app **밖**을 가리킴(verify.sh:189-193): 이건
> **경로 문제라 UID/소유권과 무관, non-root로 안 풀린다**. 따라서 mv-aside 제거의 안전성은
> "non-root라 괜찮다"가 **아니라** "attach가 in-container 서브모듈 git에 의존하지 않는다"에 달려
> 있고 이건 **미검증**(attach는 `bun run dev`로 opencode 포크 TUI를 띄움 — git 호출 가능성 존재).
> Build&Test attach에서 **실측**하라:
> - git 의존 없음 확인 → 제거 안전, 끝.
> - git 의존 있음 → 비파괴 대안 재설계. 이때 **`[ -f ]`(NOT `[ -e ]`) 가드(verify.sh:189-192)의
>   지혜를 반드시 보존** — 그 가드가 F22/F25 데이터 손실(standalone .git을 `master`로 clobber)을
>   막았다. 어떤 대안도 `rm .git` 무가드 경로를 재도입하면 안 됨.

## 4. 변경 파일 요약
- `scripts/verify-run.sh` (신규) — `DOCKER_UID/DOCKER_GID` export 래퍼 + (G-7 1차안 시) `init-perms` 선행 호출. **유일 진입점**.
- `scripts/verify.sh` — cleanup() + 상단 `trap cleanup EXIT` 삭제, run_attach의 .git mv-aside/복원 + safe.directory 삭제, attach trap을 데몬-kill만으로 교체(원자적).
- `docker-compose.verify.yml` — `user:` fail-loud 보간, `HOME=/tmp`, claude 마운트 `/tmp/.claude`, (1차안) `init-perms` root 서비스, 헤더 주석 갱신 (전 서비스: verify/attach/seed-timeline + init-perms).
- `Dockerfile.verify` — `/tmp/.claude` chmod 777 (+ 2차안 채택 시에만 볼륨 타깃 chmod). `USER` 없음.
- `scripts/worktree-setup.sh:148-151` — 안내 명령을 `verify-run.sh ...`로 교체 (**필수 코드 변경**, critic HIGH-2).

## 5. 미해결 결정 (Build&Test 결과로 확정)
- **G-7 1차/2차안**: 첫 non-root `bun install` 쓰기 실측 후 init-perms 서비스 유지 여부 결정.
- **G-1 auth**: attach 실 LLM 턴이 `~/.claude.json` 없이 인증되면 추가 마운트 불필요. 실패 시
  `~/.claude.json` 마운트(ro vs rw vs copy-to-/tmp — :rw는 호스트 실 claude 설정 오염 위험) 또는
  `CLAUDE_CONFIG_DIR` 선택. **F27 스코프 확장 여부는 사용자 결정**(기본: verify-first, 회귀 아님).
- **MEDIUM-4 git 의존**: attach가 in-container 서브모듈 git을 쓰는지 실측 후 mv-aside 제거 확정/대안.

## 6. 보안(SECURITY-15 fail-safe)
- preflight의 prod-안전 가드(`AUTOSTOCK_ENV_FILE` 필수 + `/app/.env` 부재)는 **그대로 유지** — non-root 전환과 무관하게 fail-closed 유지.
- non-root 실행은 컨테이너 권한을 오히려 축소(최소권한) → 보안상 개선.
- `user:` fail-loud(`:?`)로 래퍼 우회 시 즉시 실패 → 잘못된 UID로 인한 prod-인접 오동작 차단.
