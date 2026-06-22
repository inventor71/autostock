# F90 — Docker prod 다중 인스턴스 요구사항

> Requirements Analysis (standard~comprehensive — infra + 실(페이퍼) 계정 리스크).
> 기존 verify 하네스(F10/F15) 패턴 확장. 관련: [[f85-aggressiveness-knob]] · [[worktree-live-verification]] · F16 account_farm.

## 1. 의도
검증 하네스(`docker-compose.verify.yml` F15 `attach`)를 **prod 다중 인스턴스 런타임**으로 일반화한다.
인스턴스마다 **계정·상태·aggressiveness**를 분리해 N개를 동시에 long-running으로 띄우고, 실행 중
컨테이너에 **쉽게 attach**해 콘솔 TUI로 관찰한다.

## 2. 확정 결정 (UAQ 2026-06-18)
| # | 결정 | 값 |
|---|------|----|
| D1 | 인스턴스별 설정 분리 | **env 오버라이드** (`AUTOSTOCK_AGGRESSIVENESS` 등, F85 config 확장) |
| D2 | 기존 host balanced 데몬 | **전부 컨테이너로 이주** (상태 마이그레이션) |
| D3 | 추가 계정 소스 | **F16 account_farm** (`broker.provider=account_farm`, 인스턴스별 `BROKER_ACCOUNT_ID`) |
| D4 | 라이프사이클/attach | **long-running `up -d` + `prod-run.sh attach`** (docker exec 콘솔 TUI); `ls`/`logs`/`down` |

## 3. 기능 요구사항 (FR)

- **FR-1 (prod compose, verify와 분리).** 신규 `docker-compose.prod.yml` — verify 하네스는 그대로 두고
  별개. 서비스: prod 데몬(인스턴스화), `init-perms`(볼륨 chown, verify 패턴 재사용). 이미지는 기존
  `autostock-verify:latest` 툴체인 재사용(또는 동일 Dockerfile) — 코드 `.:/app` 마운트, 비root(host UID).

- **FR-2 (인스턴스 파라미터화).** 한 compose가 인스턴스 이름(`<name>`)으로 파라미터화:
  - **계정**: `AUTOSTOCK_ENV_FILE=/app/.env.<name>` (account_farm 키 + `BROKER_ACCOUNT_ID`).
  - **상태 볼륨**: `workspace-<name>`, `steering-<name>`, `logs-<name>` (인스턴스 간 완전 격리).
  - **설정 오버라이드**: `AUTOSTOCK_AGGRESSIVENESS=<level>` (그리고 인스턴스별로 달라야 하는 설정 —
    최소 aggressiveness; broker provider가 인스턴스마다 다르면 `AUTOSTOCK_BROKER_PROVIDER`도 — §FR-3).
  - 컨테이너/프로젝트 이름·볼륨이 `<name>`으로 네임스페이스 → N개 동시 가동 충돌 없음.

- **FR-3 (env 설정 오버라이드 — F85 확장).** `config/config.py` `get_settings()`가 settings.yaml 로드 후
  지정된 env 키를 **위에 덮어쓴다**. 1차 대상: `AUTOSTOCK_AGGRESSIVENESS`(F85 validator 재사용, fail-safe).
  인스턴스별로 broker를 달리해야 하면 `AUTOSTOCK_BROKER_PROVIDER`/계정 키도(설계에서 확정). 미설정 시
  settings.yaml 값 그대로 → 하위호환.

- **FR-4 (운영 헬퍼 `scripts/prod-run.sh`).** verify-run.sh 패턴(DOCKER_UID/GID 주입, fail-loud) 차용:
  - `up <name>` — 데몬 컨테이너 백그라운드 기동(`-d`), 볼륨 init-perms 선행.
  - `attach <name>` — 실행 중 컨테이너에 `docker exec -it`로 **콘솔 TUI** 기동(데몬과 별도 프로세스,
    파일드롭 스티어링 채널). detach해도 데몬 지속.
  - `ls` — 가동 중 인스턴스 + 상태(헬스/계정/aggressiveness) 한눈에.
  - `logs <name>` — 데몬 로그 tail.
  - `down <name>` — 인스턴스 정지(상태 볼륨 보존; `down --wipe`로 볼륨까지 제거는 명시 옵션).

- **FR-5 (host→컨테이너 상태 마이그레이션).** 기존 host balanced 데몬의 `workspace/`(저널·decisions.jsonl·
  grades.jsonl·lessons.md·positions·regime 등)와 `steering/`을 balanced 인스턴스 볼륨으로 **1회 이전**해
  에이전트 메모리(누적 학습)를 보존한다. `prod-run.sh migrate <name> <src>` 형태.

- **FR-6 (관찰성).** `ls`에 각 인스턴스의 aggressiveness·계정ID·헬스(F63/F69 산출물)·최근 턴을 표기.
  컨테이너 로그/스티어링 산출물이 인스턴스 볼륨에 격리 저장.

## 4. 안전 요구사항 (Security Baseline 후보 — 실 페이퍼 계정 취급)

- **SR-1 (중복 체결 금지 — 최우선).** 두 인스턴스가 **같은 broker 계정**(동일 `BROKER_ACCOUNT_ID`)을
  쓰면 동일 결정을 이중 체결한다. `up`은 **계정 중복을 거부**한다(이미 가동 중인 인스턴스와 같은
  account id면 fail-loud). 인스턴스↔계정은 1:1.
- **SR-2 (마이그레이션 전 host 데몬 중단).** balanced를 컨테이너로 이주할 때, **같은 계정에서 host
  프로세스와 컨테이너 데몬이 동시에 돌면 안 된다.** `migrate`/`up balanced`는 host 데몬이 멈춰 있는지
  확인(또는 운영자에게 명시 확인) 후 진행.
- **SR-3 (시크릿 격리).** `.env.<name>`은 인스턴스별 계정 시크릿 — 레포에 커밋 금지(`.gitignore`),
  예시 `.env.<name>.example`만 제공. 컨테이너는 Settings 통해서만 크레덴셜 읽음(verify 패턴: OS env
  주입 안 함).
- **SR-4 (verify 하네스 무영향).** prod compose는 verify와 **별도 파일·별도 볼륨**. 기존
  `docker-compose.verify.yml`/`.env.test`/TEST 계정 경로를 전혀 건드리지 않는다.

## 5. 비기능 요구사항 (NFR)
- **NFR-1 (하위호환).** env 오버라이드 미설정 → 현행 동작. prod compose는 신규 파일이라 기존 실행 경로 무영향.
- **NFR-2 (이미지 재사용).** 새 무거운 이미지 빌드 회피 — 기존 verify 툴체인 이미지/Dockerfile 재사용.
- **NFR-3 (WSL2/Docker 환경).** 현 개발환경(WSL2 + Docker, `setup-docker-wsl2.md`)에서 동작. 비root·host UID.
- **NFR-4 (리소스).** N개 동시 시 LLM 호출(구독/토큰)·CPU 부담 — `ls`에 가동 수 노출, 무한 증식 방지 가이드.

## 6. 범위 외 (후속)
- 원격 호스트/오케스트레이션(k8s, swarm), 자동 스케일링.
- 인스턴스 간 자본/포지션 동기화(각 인스턴스는 독립 계정·독립 책).
- 웹 대시보드에서 멀티 인스턴스 선택(F86/F79 위 후속).
- aggressiveness 외 다량의 per-instance 설정 분리(필요 시 settings 파일 마운트로 확장).

## 7. Open (설계에서 확정)
- broker provider를 인스턴스마다 다르게 할지(balanced=현 계정 유지 vs 전부 account_farm) → env override 범위.
- balanced 이주 시 계정 유지(책 보존) vs 새 account_farm 계정(책 리셋) — FR-5/SR-2와 결합.
- 콘솔 TUI를 `docker exec`로 띄울 때 MCP/스티어링 토큰 배선(F18 attach 패턴 재사용).
