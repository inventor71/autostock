# F90 — Infrastructure / Functional Design

> verify 하네스(F10/F15/F18) 패턴 확장. Security Baseline Enabled. 관련: [[f85-aggressiveness-knob]].

## 0. 구조 한눈에
```
docker-compose.prod.yml          ← NEW: prod 다중 인스턴스 (verify와 별개 파일·볼륨)
  service: daemon                   python main.py --mode agent --steering (백그라운드)
  service: init-perms               볼륨 chown (verify 패턴 재사용, root 1회)
  volumes: workspace/steering/logs  상대명 → COMPOSE_PROJECT_NAME으로 인스턴스별 네임스페이싱
scripts/prod-run.sh              ← NEW: up / attach / ls / logs / down / migrate
config/config.py                 ← env override (get_settings)
.env.<name>                      ← 인스턴스별 계정 시크릿 + AUTOSTOCK_* 프로세스 env (git 제외)
.env.<name>.example              ← 커밋되는 템플릿
```
인스턴스 격리 = **COMPOSE_PROJECT_NAME=autostock-`<name>`** 한 방으로: docker가 볼륨을
`autostock-<name>_workspace`, 컨테이너를 `autostock-<name>-daemon-1`로 네임스페이싱 → 단일 compose
파일로 N개 동시, 충돌 0.

## 1. env override (FR-3, F85 확장) — `config/config.py`
`get_settings()`는 `Settings(**yaml_config)`이므로, **yaml dict에 주입 후** 생성(validator 자연 실행):
```python
_ENV_OVERRIDES = {                       # env var -> (yaml section, key)
    "AUTOSTOCK_AGGRESSIVENESS": ("agent", "aggressiveness"),
    "AUTOSTOCK_BROKER_PROVIDER": ("broker", "provider"),
}
def _apply_env_overrides(cfg: dict) -> None:
    for env, (section, key) in _ENV_OVERRIDES.items():
        v = os.environ.get(env)
        if v:
            cfg.setdefault(section, {})[key] = v

def get_settings() -> Settings:
    yaml_config = load_yaml_config(CONFIG_DIR / "settings.yaml")
    _apply_env_overrides(yaml_config)    # F90
    return Settings(**yaml_config)
```
- `AUTOSTOCK_AGGRESSIVENESS`는 F85 `field_validator`가 받으므로 오타→balanced fail-safe 그대로.
- 미설정 → yaml 값 → 현행(NFR-1). 계정 키(BROKER_*)는 pydantic이 `.env.<name>`에서 직접 로드(override 대상 아님).

## 2. docker-compose.prod.yml (FR-1/2, SR-4)
- **verify와 완전 분리**: 별도 파일, 상대 볼륨명(프로젝트 네임스페이싱), `.env.test`/attach-* 볼륨 미참조.
- 이미지: 기존 `autostock-verify:latest` 재사용(NFR-2; 동일 툴체인). 빌드 필요 시 동일 Dockerfile.verify.
- `daemon` 서비스:
  - `image: autostock-verify:latest`, `volumes: [.:/app, workspace:/app/workspace, steering:/app/steering, logs:/app/logs, ~/.claude:/tmp/.claude:ro]`
  - `user: "${DOCKER_UID:?via prod-run.sh}:${DOCKER_GID:?via prod-run.sh}"`, `working_dir: /app`
  - `environment: AUTOSTOCK_ENV_FILE=/app/.env.${INSTANCE}, AUTOSTOCK_AGGRESSIVENESS=${AUTOSTOCK_AGGRESSIVENESS:-}, AUTOSTOCK_BROKER_PROVIDER=${AUTOSTOCK_BROKER_PROVIDER:-account_farm}, STEERING_OPERATOR_TOKEN=${STEERING_OPERATOR_TOKEN:?}`
  - `labels: [autostock.instance=${INSTANCE}, autostock.account=${AUTOSTOCK_ACCOUNT_ID}]`  ← SR-1 dedup 키
  - `command: ["python","main.py","--mode","agent","--steering"]`
  - `restart: unless-stopped` (long-running), `stdin_open/tty` 불필요(데몬은 백그라운드; attach는 exec).
- `init-perms`: verify의 것과 동일(상대 볼륨 chown), root 1회.

## 3. scripts/prod-run.sh (FR-4) — verify-run.sh 패턴
공통: `DOCKER_UID/GID` export, `.env.<name>` 로드해 `AUTOSTOCK_*`/`AUTOSTOCK_ACCOUNT_ID`(=BROKER_ACCOUNT_ID)
프로세스 env로 승격, `COMPOSE_PROJECT_NAME=autostock-<name>`.
- **`up <name>`**:
  1. `.env.<name>` 존재 확인(없으면 fail + `.example` 안내).
  2. **SR-1 계정 dedup**: `docker ps --filter label=autostock.account=<id>`에 *다른* 인스턴스가 그 계정을
     이미 쓰면 **거부**(fail-loud). 인스턴스↔계정 1:1.
  3. **SR-2 host 데몬 체크**(balanced 등 이주 계정): 동일 계정의 host `python main.py --mode agent`
     프로세스가 떠 있으면 경고+확인(중복 체결 방지).
  4. init-perms → `docker compose -f docker-compose.prod.yml up -d`.
- **`attach <name>`**: `docker exec -it autostock-<name>-daemon-1 <console-launch>` — 콘솔 TUI를 데몬과
  같은 컨테이너에서 별도 프로세스로(공유 steering dir + STEERING_OPERATOR_TOKEN; F18 attach 배선 재사용).
  detach(Ctrl-p Ctrl-q 또는 콘솔 종료)해도 데몬 지속. (정확한 console 명령은 code-gen에서 verify `attach`
  command 구현 참조해 확정.)
- **`ls`**: `docker ps --filter label=autostock.instance` → 인스턴스명·계정(마스킹)·aggressiveness·상태·헬스.
- **`logs <name>`**: `docker logs -f autostock-<name>-daemon-1`.
- **`down <name>`**: `docker compose -p autostock-<name> down` (볼륨 보존). `down --wipe <name>` → `-v`로 볼륨 제거(명시).
- **`migrate <name> <src>`** (FR-5): host `workspace/`+`steering/`을 인스턴스 볼륨으로 1회 복사.
  - 가드: 대상 볼륨이 **비어 있어야**(덮어쓰기 금지); SR-2 host 데몬 정지 확인.
  - 구현: `docker run --rm -v autostock-<name>_workspace:/dest -v <src>/workspace:/src:ro busybox sh -c 'cp -a /src/. /dest/'` (+ steering).

## 4. 시크릿 (SR-3)
- `.env.<name>`: `BROKER_API_KEY/SECRET`, `BROKER_ACCOUNT_ID`(인스턴스별 distinct), `AUTOSTOCK_AGGRESSIVENESS`,
  `AUTOSTOCK_BROKER_PROVIDER`(보통 account_farm), `STEERING_OPERATOR_TOKEN`(인스턴스별).
- `.gitignore`: `.env.*` 무시하되 `!.env.*.example` 예외. `.env.<name>.example` 템플릿 커밋.

## 5. Open 해소 (요구사항 §7)
- **balanced=현 계정 유지(책 보존)**: balanced 인스턴스 `.env.balanced`는 현 host `.env`의 provider/키를
  그대로(alpaca든 account_farm이든) → `AUTOSTOCK_BROKER_PROVIDER`로 provider 맞춤. 책·workspace 보존.
- 신규 aggressive 인스턴스: account_farm + 새 `BROKER_ACCOUNT_ID`(빈 책에서 시작).
- env override 범위 = aggressiveness + broker provider (둘).

## 6. 테스트 계획
- **unit** (`config/config.py`): `_apply_env_overrides` — AUTOSTOCK_AGGRESSIVENESS/BROKER_PROVIDER 주입 시
  Settings 반영, 미설정 시 yaml 유지, 오타 aggressiveness→balanced(F85 validator). `get_settings` monkeypatch env.
- **compose 정합**: `docker compose -f docker-compose.prod.yml config`가 파싱되는지(드라이). 볼륨/라벨/env 보간 확인.
- **prod-run.sh 단위**: SR-1 dedup 로직(같은 account label이면 거부) — docker mock 또는 bats 없으면 함수 분리해 셸 단위 점검.
- **스모크(실 account_farm 1회)**: `up test-instance`(샌드박스 계정) → `ls`에 표기 → `attach`로 콘솔 →
  `down`. host/verify 무영향 확인.
- 회귀: 기존 verify 하네스(`scripts/verify-run.sh run --rm verify unit`) 여전히 green.

## 7. NFR/Security 컴플라이언스 요약
- SR-1 계정 1:1(라벨 dedup) / SR-2 host 동시가동 체크 / SR-3 시크릿 git 제외 / SR-4 verify 무영향(별 파일·볼륨).
- NFR-1 override 미설정=현행 / NFR-2 이미지 재사용 / NFR-3 WSL2·비root / NFR-4 `ls`로 가동 수 가시화.
