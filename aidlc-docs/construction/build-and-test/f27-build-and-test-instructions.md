# F27 Build & Test 가이드 — verify-harness non-root

> **상태(2026-06-01)**: 1·2·3·4단계(build / ⭐G-7 typecheck / unit / 호스트소유·sudo-free)는
> AI가 uid 1000:989로 **직접 실행해 PASS** 확인 완료(typecheck 19/19, unit 556, find -user root 공백).
> 그 과정에서 2건 픽스됨: Dockerfile `npm i -g node-gyp`(bun 네이티브 빌드 ENOENT), verify-run.sh
> 마운트포인트 호스트소유 선생성. **남은 사용자 실행 = 5 smoke·6 G-1 attach·7 MED-4·8 최종 remove**
> (real TEST 키 + claude auth 필요). ⭐ = make-or-break.

## 0. 준비
```bash
# F27 worktree에서, 서브모듈을 HOST에서 먼저 init (컨테이너는 gitdir-escape로 init 불가)
cd /home/jihoonpark/Project/autostock
scripts/worktree-setup.sh F27 --docker-verify     # 서브모듈 init + .env.test 스캐폴드 + 안내 출력
cd .claude/worktrees/F27
# .env.test에 TEST paper 계정 키 + EXPECTED_ACCOUNT_NUMBER 채워졌는지 확인 (smoke/attach용)
```

## 1. Build
```bash
scripts/verify-run.sh build
```
- **PASS**: 이미지 빌드 성공 (claude/bun/torch 레이어).

## 2. ⭐ G-7 — non-root 볼륨 쓰기 (가장 먼저 깨질 곳)
init-perms가 named volume을 호스트 UID로 chown하는지, 그 위에 non-root `bun install`이 쓰는지.
```bash
# 래퍼가 자동으로 init-perms를 선행하지만, 수동으로도 확인:
scripts/verify-run.sh run --rm init-perms; echo "init-perms exit=$?"

# 볼륨 소유권이 내 UID인지 확인:
docker run --rm -v f27_verify-node-modules:/v alpine sh -c 'stat -c "%u:%g" /v'
#   → 내 $(id -u):$(id -g) 여야 함 (root 0:0 이면 G-7 1차안 실패 → 아래 Fallback)

# 실제 쓰기(typecheck가 bun install 수행):
scripts/verify-run.sh run --rm verify typecheck
```
- **PASS**: `bun install`이 EACCES 없이 완료 + typecheck 통과.
- **FAIL (EACCES / 볼륨이 0:0)**: G-7 1차안(init-perms)이 안 먹은 것.
  - 볼륨 이름 prefix가 다를 수 있음(`docker volume ls | grep node-modules`)→ init-perms의
    실제 볼륨명 확인. compose 프로젝트명이 `f27`이 아니면 `<project>_verify-node-modules`.
  - 그래도 안 되면 **2차안**: `Dockerfile.verify`에 `RUN mkdir -p
    /app/operator-console/cli/node_modules ... && chmod 777 ...` 추가 후 rebuild — 단 bind-shadow로
    안 먹을 가능성 큼(설계 §2 G-7). 결과를 알려주면 init-perms 시퀀싱을 보강하겠습니다.

## 3. Unit (offline pytest)
```bash
scripts/verify-run.sh run --rm verify unit
```
- **PASS**: pytest 통과. (`__pycache__`는 호스트 소유로 생기거나 PYTHONDONTWRITEBYTECODE로 미생성)

## 4. ⭐ 호스트 소유 확인 — `git worktree remove` sudo 불필요 (이 트랙의 핵심 목표)
```bash
# typecheck/unit 실행 뒤 worktree에 root-소유 파일이 없는지:
find . -xdev -user root -print 2>/dev/null | head      # 아무것도 안 나와야 함
# 정식 확인은 트랙 종료 시: (지금 지우지 말 것 — 아직 attach 테스트 남음)
#   cd /home/jihoonpark/Project/autostock && git worktree remove .claude/worktrees/F27   # sudo 없이 성공해야
```
- **PASS**: `-user root` 출력 없음. (있으면 어떤 경로인지 알려주세요 → 누락 writer 추적)

## 5. Smoke (REAL claude + read-only Alpaca, TEST 계정)
```bash
scripts/verify-run.sh run --rm verify smoke
```
- **PASS**: `claude --version` OK + account_number == EXPECTED_ACCOUNT_NUMBER. (주문 없음)
- 참고: smoke의 claude는 `--version`만이라 auth 불필요 → G-1은 다음 단계에서 진짜 검증됨.

## 6. ⭐ G-1 — attach 실 LLM 턴 인증 (verify-first의 분기점)
```bash
scripts/verify-run.sh run --rm -it attach
```
관찰 포인트:
- **데몬 기동 + snapshot 발행**(최대 180s) → 콘솔 TUI에 사이드바가 뜨면 **G-1 PASS** (인증 OK).
- **FAIL 신호**: 로그(`/app/logs/daemon.attach.log`, 컨테이너 종료 시 출력)에 "not logged in" /
  onboarding / 401 / auth. 이건 `~/.claude.json`(HOME 루트, 미마운트) 때문일 수 있음.
  - **즉시 픽스**: `docker-compose.verify.yml`의 `attach` 볼륨에 한 줄 추가 —
    `- ${HOME}/.claude.json:/tmp/.claude.json:rw` (주의: :rw는 컨테이너가 호스트 실제 claude
    설정을 수정할 수 있음. 꺼림칙하면 먼저 `:ro`로 시도, 그래도 claude가 쓰기 요구하면 rw).
  - 재실행 후 인증되면 그 한 줄을 F27에 포함하겠습니다(알려주세요).

## 7. ⭐ MEDIUM-4 — attach가 in-container 서브모듈 git을 쓰나
attach 중(opencode TUI 떠 있을 때) 콘솔/로그에 git 관련 에러가 있는지 관찰:
- git 에러 **없음** → `.git` 우회 제거 안전, 확정.
- git 에러 **있음**(예: "not a git repository", gitdir 못 찾음) → 비파괴 대안 재설계 필요.
  로그를 알려주세요. (절대 `rm .git` 금지 — F22/F25 데이터 손실 원인)

## 8. 종료 + 최종 sudo-free 확인
```bash
# attach는 Ctrl-C로 종료(데몬도 함께 kill). 그 뒤:
cd /home/jihoonpark/Project/autostock
find .claude/worktrees/F27 -xdev -user root | head      # 비어야 함
# 트랙 머지/폐기 시:
git worktree remove .claude/worktrees/F27               # ⭐ sudo 없이 성공 = R-1/R-2 해소 입증
```

## 결과 보고 양식 (이거 채워서 주세요)
| 단계 | 결과 | 비고 |
|------|------|------|
| 1 build | PASS/FAIL | |
| 2 ⭐G-7 typecheck | PASS/FAIL | 볼륨 소유 uid: |
| 3 unit | PASS/FAIL | |
| 4 ⭐호스트소유 | PASS/FAIL | root 파일: |
| 5 smoke | PASS/FAIL | |
| 6 ⭐G-1 attach 인증 | PASS/FAIL | .claude.json 추가했나: |
| 7 ⭐MED-4 git | 에러없음/에러있음 | |
| 8 worktree remove sudo-free | PASS/FAIL | |

> 2·6·7에서 FAIL이면 해당 로그를 붙여 주세요 — init-perms 시퀀싱(G-7) / `.claude.json`
> 마운트(G-1) / 비파괴 git 핸들러(MED-4)를 즉시 보강해 재검증하겠습니다.
