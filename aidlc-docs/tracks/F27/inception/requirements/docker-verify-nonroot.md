# F27 — docker-verify 하네스 non-root 실행 (Requirements)

> Type: 인프라 BUG fix / refactor. 검증 비중이 큼(4개 실행 모드 × non-root 동작).

## 1. 문제 (현재 상태)

`Dockerfile.verify`에 `USER` 지시가 없어 컨테이너가 **root로 실행**된다. 코드는 bind-mount
(`.:/app`)이므로 컨테이너가 워크트리에 쓰는 모든 파일이 **root:root 소유**가 된다. 결과:

- **R-1**: 호스트에서 `git worktree remove`가 sudo 없이 실패 (node_modules/.ts-dist/.turbo/
  __pycache__ 등 root 소유 빌드 산출물).
- **R-2 (심각)**: 컨테이너 내 git(root)이 호스트 소유 `.git`을 "dubious ownership"으로 거부 →
  verify.sh가 우회(rm+init)하다가 **서브모듈 git을 파괴**. F22·F25에서 두 번 발생, 워킹트리로 복구.

## 2. 누적된 우회 코드 (제거 대상)

root-소유를 사후 수습하려고 verify.sh/compose에 쌓인 것들:

| 위치 | 우회 | 제거 가능? |
|------|------|-----------|
| `scripts/verify.sh` `cleanup()` (F17) | `find /app -xdev -exec chown $host_owner` 전체 handback + .turbo/node_modules/tsbuildinfo/__pycache__ rm 스윕 | non-root면 불필요 → 제거 |
| `scripts/verify.sh` `run_attach()` | 서브모듈 `.git` 비파괴 백업/복원(mv aside + EXIT trap) + `safe.directory '*'` (F25 임시방편) | non-root + 호스트 소유 .git이면 dubious-ownership 안 뜸 → 제거 |
| `docker-compose.verify.yml` | `PYTHONDONTWRITEBYTECODE`, `HYPOTHESIS_STORAGE_DIRECTORY=/tmp/...` (root 쓰기 회피) | 호스트 소유면 워크트리에 써도 OK지만, 잔여물 정리 관점에서 유지 여부는 설계 판단 |
| `docker-compose.verify.yml` | named-volume 마스킹(node_modules → verify-node-modules/mcp-node-modules, steering/workspace/logs) | 일부는 root-소유 회피용이 아니라 arch-clash/격리용 → **선별 유지** (아래 §4) |

## 3. 원하는 해결 (FR)

- **FR-1**: 컨테이너를 **호스트 사용자(UID:GID)로 실행**한다. docker-compose에
  `user: "${UID:-1000}:${GID:-1000}"` (또는 `.env`/래퍼에서 `id -u`/`id -g` 주입). 생성 파일이
  처음부터 호스트 소유 → R-1/R-2 소멸.
- **FR-2**: FR-1으로 불필요해진 우회 코드 제거 — `cleanup()`의 chown handback, `.git` 백업/복원,
  `safe.directory` (§2 표의 "제거 가능" 항목).
- **FR-3**: 4개 모드(typecheck/unit/smoke/attach)가 non-root에서 **모두 통과**해야 한다(회귀 없음).

## 4. non-root 전환 시 검증/해결할 gotcha (테스트 핵심)

이미지 툴체인은 **root로 빌드**됨(/usr/local/bun, npm global claude, pip site-packages). non-root가
실행만 하면 보통 OK(읽기+실행)지만, 쓰기/HOME 경로에서 막힐 수 있다:

- **G-1 (HOME)**: compose가 `${HOME}/.claude:/root/.claude` 마운트 → `/root`는 root 홈.
  non-root UID는 `/root` 접근 불가일 수 있음. **HOME을 명시**하고(`HOME=/tmp` 또는 마운트 타깃을
  `$HOME/.claude`로) claude CLI가 설정/캐시를 읽고 쓰게 해야 함. claude는 세션 캐시를 **쓰므로**
  마운트 위치가 그 UID로 쓰기 가능해야 함 (attach 모드는 이미 :rw).
- **G-2 (bun/npm 캐시)**: `bun install`이 `~/.bun`·전역 캐시에 씀. HOME이 안 잡히면 실패. HOME
  지정 + 캐시 디렉터리 쓰기 권한 필요.
- **G-3 (pip)**: pip 설치는 빌드 타임(root)에 끝났으므로 런타임 pip 불필요. 단 `__pycache__` 생성은
  PYTHONPATH=/app 실행 시 워크트리에 씀 → 호스트 소유면 무해.
- **G-4 (/app 쓰기)**: 컨테이너가 `/app/.env`(verify.sh가 .env.test→.env 복사), `/app/logs`,
  steering/workspace 등에 씀. 호스트 UID로 실행하면 호스트 소유 → OK. (`.env`는 gitignore.)
- **G-5 (git 사용자)**: in-container git이 commit을 만들면(attach의 "container snapshot" 등)
  `user.name/email` 미설정으로 실패 가능 → non-root면 애초에 그 우회가 사라지므로 해당 없음.
- **G-6 (UID 주입 이식성)**: `${UID}`는 셸 변수라 compose가 자동 인식 못 할 수 있음 → `.env` 파일에
  `UID=`/`GID=`를 쓰거나, 실행 래퍼(`scripts/verify-run.sh`)에서 `UID=$(id -u) GID=$(id -g)
  docker compose ...`로 주입. **설계 결정 필요.**

## 5. 미해결 (설계 시 확정)

- **D-1 (UID override 방식)**: `.env`(UID/GID) vs 래퍼 스크립트 vs compose 기본값. 이식성/사용성 trade-off.
- **D-2 (named volume 유지 범위)**: node_modules 볼륨은 host/container arch-clash 방지 목적도 있음
  (bun 네이티브 애드온). non-root여도 유지할지, bind로 되돌릴지. attach의 steering/workspace/logs
  볼륨은 격리 목적 — 유지 권장.
- **D-3 (HOME 처리)**: claude/bun이 쓸 HOME을 어디로 둘지 + 해당 경로 쓰기 권한 확보 방법.

## 6. 관련 파일
- `Dockerfile.verify` — USER/HOME, (선택) 빌드 ARG로 uid
- `docker-compose.verify.yml` — `user:`, HOME env, 볼륨 정리
- `scripts/verify.sh` — cleanup() handback 제거, run_attach() .git 백업/safe.directory 제거
- (선택) `scripts/verify-run.sh` 또는 `.env` — UID/GID 주입

## 7. 위험 / 비고
- 위험도 **Medium**: prod 무관(검증 하네스 전용)이나 4모드 회귀·non-root 권한 함정이 많아 테스트 필수.
- F25에서 넣은 임시방편(safe.directory, .git 비파괴 백업)을 이 트랙이 **근본 해결로 대체**.
- 롤백 쉬움(parent repo 3파일, worktree/브랜치 격리).
