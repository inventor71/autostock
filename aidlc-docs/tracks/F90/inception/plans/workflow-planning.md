# F90 — Workflow Planning

## 단계
| 단계 | 실행 | 깊이 | 근거 |
|------|------|------|------|
| Workspace Detection | ✅ | — | brownfield, docker-verify 자산 RE 완료 |
| Reverse Engineering | ⏭️ | — | 기존 compose/Dockerfile/verify-run.sh 직접 분석으로 충분 |
| Requirements Analysis | ✅ | standard~comp | UAQ 4건 + SR 4건 |
| User Stories | ⏭️ skip | — | 운영자 단일, 신규 페르소나 없음(인프라 CLI) |
| Workflow Planning | ✅ | — | 본 문서 |
| Application/Functional Design | ✅(경량) | — | env override 로직만 코드; 나머지 인프라 |
| **Infrastructure Design** | ✅ | standard | 핵심 — compose 구조/볼륨/네임스페이싱/안전 게이트 |
| Units Generation | ⏭️ skip | — | 단일 응집(인프라 1묶음) |
| Code Generation | ✅ | — | worktree feat/F90 |
| Build & Test | ✅ | — | env-override 단위테스트 + compose 정합/스모크(실 account_farm 1회) |

## 변경 시퀀스
1. **env override** — `config/config.py` `get_settings()`에 `_apply_env_overrides` (AUTOSTOCK_AGGRESSIVENESS / AUTOSTOCK_BROKER_PROVIDER). 단위테스트.
2. **prod compose** — `docker-compose.prod.yml` (daemon 서비스 + init-perms, COMPOSE_PROJECT_NAME 네임스페이싱, 상대 볼륨, `.:/app`, 비root).
3. **운영 헬퍼** — `scripts/prod-run.sh` (up/attach/ls/logs/down/migrate) + 안전 게이트(SR-1 계정 dedup 라벨, SR-2 host 체크).
4. **시크릿 스캐폴드** — `.env.<name>.example`, `.gitignore`에 `.env.*`(단 `.example` 제외) 확인.
5. **문서** — post-merge-guide(운영 절차: 이주→up→attach), build-and-test.

## 산출물
- 설계: `construction/infra-design/infra-design.md`
- 코드: worktree `feat/F90` — `docker-compose.prod.yml`, `scripts/prod-run.sh`, `config/config.py`(override), `.env.*.example`, 테스트.
