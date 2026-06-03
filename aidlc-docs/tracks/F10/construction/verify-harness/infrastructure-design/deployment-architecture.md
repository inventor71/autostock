# F27 Deployment Architecture — verify-harness

> 클라우드 배포 없음. "배포 아키텍처" = 로컬 개발자 머신의 docker-compose 검증 하네스 실행 토폴로지.

## 실행 토폴로지

```
호스트(jihoonpark, WSL2)  ─── scripts/verify-run.sh (DOCKER_UID/GID export)
        │
        ▼
docker compose -f docker-compose.verify.yml
        │
        ├── verify        (user=호스트UID:GID, HOME=/tmp)
        │     mounts: .:/app(bind)  ${HOME}/.claude→/tmp/.claude:ro
        │             verify-node-modules, mcp-node-modules (named, arch-iso)
        │     modes: typecheck | unit | smoke | all
        │
        ├── attach        (user=호스트UID:GID, HOME=/tmp, tty)
        │     + ${HOME}/.claude→/tmp/.claude:rw
        │     + attach-steering/workspace/logs (named, 격리)
        │     daemon(main.py --mode agent --steering) bg + console TUI fg
        │     account: TEST paper only (AUTOSTOCK_ENV_FILE=/app/.env.test, preflight fail-closed)
        │
        └── seed-timeline (user=호스트UID:GID) — workspace 볼륨 시드
```

## 핵심 불변식
- **prod 무영향**: 모든 서비스가 `.env.test`만 로드, preflight가 prod `.env` 존재 시 fail-closed.
- **파일 소유**: bind-mount(/app) 산출물 = 호스트 UID 소유 → `git worktree remove` sudo 불필요.
- **격리 볼륨**: node_modules·attach 런타임은 named volume → 워크트리 git 상태 비오염.
- **최소권한**: 컨테이너는 non-root 실행(빌드만 root).

## 환경 변수
| 변수 | 값 | 용도 |
|------|----|----|
| DOCKER_UID / DOCKER_GID | `id -u`/`id -g` (래퍼) | `user:` 보간 |
| HOME | /tmp | claude/bun 설정·캐시 쓰기 경로 |
| AUTOSTOCK_ENV_FILE | /app/.env.test | TEST 계정 고정(fail-closed) |
| TZ | ${TZ:-Asia/Seoul} | attach 타임라인 로컬 시각 |
| STEERING_OPERATOR_TOKEN | attach-test-token(기본) | attach 데몬↔콘솔 공유 토큰 |

## 검증 게이트 (Build&Test)
4모드(typecheck/unit/smoke/attach) × non-root 전부 통과 + G-1~G-7 실측 + `git worktree remove`
sudo-free 확인. 상세는 `infrastructure-design.md` §2.
