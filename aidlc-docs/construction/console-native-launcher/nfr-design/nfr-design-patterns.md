# F5 NFR Design — Patterns (유닛 `console-native-launcher`)

> critic #1/#4/#6 보강이 정밀 설계로 반영됨. 안전 엔진/주문 경로/채널 계약 불변(BR-10/12).

## P1 — Fail-closed 기동 오케스트레이션 (NFR-A, BR-1, SECURITY-15)
런처 `cli.ts`는 **순차 파이프라인**: `resolveConfig → preflight → ensureDaemon → launchConsole(exec 핸드오프)`.
- **TTY exec 핸드오프 (critic2 #1)**: `launchConsole`이 마지막 단계 — **런처 프로세스를 콘솔 TUI로 `exec` 치환**(stdio
  상속). **launcher-side "watch" 루프 없음**(런처가 TUI와 TTY/stdin/SIGWINCH를 경합하면 콘솔이 깨짐). 런타임 끊김
  감시는 전부 콘솔(P7) 안. exit-13 = 콘솔 exec/종료 비-0 전파.
- 각 `blocking` 실패는 **사람용 한 줄 진단 + remediation**을 stderr로 출력하고 **비-0 종료**.
- **종료 코드 규약**(silent exit 불가능하게 명시):
  - `0` 정상, `10` config 해석 실패, `11` preflight blocking 실패, `12` 데몬 기동/health-wait 실패,
    `13` 콘솔 실행 실패(exec 자체 실패). 콘솔 정상 종료는 콘솔의 종료코드를 그대로 전파.
- 모든 분기에 진단이 붙는다(예외/throw도 최상위 try에서 잡아 진단 출력 후 비-0). **무진단 경로 0개.**

## P2 — 데몬 헬스 = snapshot 신선도 (critic #1, E4/BR-2.1, NFR-A)
- **판정 입력**: `${STEERING_DIR}/snapshot.json` (기존 `filedrop.ts` 리더 재사용). 페이로드의 `published_at`
  (`channel.py:180`가 `datetime.now().isoformat()`로 stamp) 또는 파일 mtime(폴백). `atomic_write_text`가 매 발행 mtime 갱신(`jsonl.py:31`).
- **naive-local 시각 처리 (critic2 #6)**: `published_at`는 **오프셋 없는 naive-local ISO**. JS `new Date(published_at)`는
  이를 **local로 파싱**하므로 `Date.now()-…` 비교가 맞다 — **반드시 local로 파싱**(기존 `sidebar/autostock.tsx:92`와 동일).
  `…+"Z"`/UTC 가정 금지(KST면 9h 어긋나 항상 stale/fresh로 뒤집힘; window 45/60s보다 큼). 30s 된 타임스탬프=fresh 단위테스트 고정.
- **신선 정의**: `now - published_at < health_window`. **`health_window`는 5s 발행 주기가 아니라 단일 bus 워커의
  최악 점유에 맞춤** — executor `_funnel(timeout=180)` + in-flight 브로커(~11s) 동안 발행이 지연되므로,
  기본 `health_window = 45s`(보수적; cold-start premarket research가 분 단위일 수 있어 health-wait는 별도 상한).
- **health-wait 알고리즘**(false-wedged 방지):
  - active이지만 첫 관측이 stale → 즉시 wedged로 단정하지 말고 **폴 루프**: 매 `poll=1s`, `published_at`이
    **전진**하거나 **연속 2회 신선** 관측되면 healthy로 확정.
  - 전체 상한 `healthwait_timeout = 60s`(cold-start 배치 흡수). 상한 초과 시에만 wedged 진단(BR-2):
    "서비스는 active이나 snapshot 발행이 멈춤(>{n}s). 데몬 로그 확인: `journalctl --user -u autostock-daemon`."
  - **bare mtime 단독 판정 금지** — content 불변이어도 mtime은 오르지만, 우리는 발행 *전진*을 본다.

## P3 — systemd user 서비스 관리 (critic #4, E3/BR-3/BR-5/BR-9)
- **유닛 생성**(`~/.config/systemd/user/autostock-daemon.service`, `ensure_installed`, 멱등):
  ```ini
  [Unit]
  Description=autostock trading daemon (agent + steering)
  After=default.target
  [Service]
  Type=simple
  WorkingDirectory={AUTOSTOCK_ROOT}            # ★ critic #4: load_dotenv는 CWD 기준 → 필수
  ExecStart={PYTHON} {AUTOSTOCK_ROOT}/main.py --mode agent --steering
  Restart=on-failure
  RestartSec=5
  [Install]
  WantedBy=default.target
  ```
  - `{PYTHON}` = repo venv 인터프리터(존재 검증; 없으면 진단). `--steering`은 TTY/stdin 비의존
    (`agent.py:195` `while True: time.sleep(1)`) → `Type=simple` 적합. **파이썬 코드 변경 0.**
  - **`EnvironmentFile` 제거 (critic2 #3)**: systemd EnvironmentFile 파서는 dotenv가 아님(`export `/따옴표/멀티라인/
    `${VAR}` 처리 상이). 데몬은 `main.py:366` `load_dotenv()`로 스스로 `.env`를 로드하므로 `EnvironmentFile`은 중복이며,
    `.env`에 비-trivial 라인이 추가되면 두 파서가 어긋나 systemd 부트 실패. → **`WorkingDirectory` + `load_dotenv`만
    authoritative.** (현재 `.env`는 0 export/0 quote라 지금은 어느 쪽이든 동일하지만 잠재 리스크 제거.)
  - 생성 후 `systemctl --user daemon-reload` → `enable` → `loginctl enable-linger {USER}`(로그아웃/부팅 생존).
- **`ensure_running`**: `systemctl --user is-active` → `inactive`면 `start`(멱등, BR-9.1: "already running" 비-에러)
  → P2 health-wait. `active`면 health 확인만(중복 start 안 함). `failed`면 진단 + 비-0(자동 start로 가리지 않음).

## P4 — 토큰 canonical 소스 + 비밀 마스킹 (critic #6, BR-6/BR-11, SECURITY-03)
- **canonical = root `.env`의 `STEERING_OPERATOR_TOKEN`**. 런처가:
  1. root `.env`에서 읽어 **메모리 보관**(출력 금지).
  2. 콘솔 프로세스 env로 **주입**(= 콘솔/MCP가 실제 쓰는 값).
  3. `cli/.env`/`.opencode/opencode.jsonc`(`{env:}` 경유)가 canonical과 **일치하는지 검사** → 불일치 시
     **warn**(blocking 아님; 주입값이 우선하므로) + drift 진단.
- **inject set 전체 (critic2 #2 — 무음 실패 차단)**: 토큰만으로 부족. 콘솔로 **`AUTOSTOCK_ROOT` + `STEERING_DIR` +
  `STEERING_OPERATOR_TOKEN`을 모두** export하고 **cwd = `${AUTOSTOCK_ROOT}/operator-console/cli`** 에서 실행해야
  `.opencode/opencode.jsonc:20`의 `{env:AUTOSTOCK_ROOT}` 절대 MCP 경로가 풀려 `autostock_steer`가 등록된다(상대경로/
  미설정 → "Module not found" → MCP 미기동 → 모델이 "주문 못함" 무음). 기동 후 MCP 미등록이면 **시끄럽게 경고**(P7).
- token_match preflight = "canonical 존재 && (주입 경로 일관)" boolean. **값 미출력**, 길이/존재/일치만.
  상수시간 비교는 단일-유저 로컬에서 무의미 → 무비용이면 유지, 필수 아님.

## P5 — 프리플라이트 체크 모델 (E1/E2)
- 각 체크 = 순수 함수 → `PreflightCheck{id,status,detail,remediation,severity}`. blocking: `token_canonical`,
  `steering_dir`, `mcp_path`. (daemon_health는 P3에서 별도.)
- `mcp_path`: `AUTOSTOCK_ROOT` set && `operator-console/src/mcp-server.ts` 존재 — 메모리 기록 회귀(상대경로→
  "Module not found"→MCP 미기동→모델이 "주문 못함") 사전 차단.
- 집계: blocking 하나라도 fail → `report.ok=false` → exit 11 + 모든 fail 진단 일괄 출력.

## P6 — 사이드바 우선 / home-skip (BR-7.1) — ⚠ 메커니즘 정책 분기 (critic2 #5)
- **라운드1 전제 뒤집힘**: `home.tsx`는 중앙 컬럼이고 `sidebar_content` consumer가 없음(`session/sidebar.tsx:92`에서만
  소비, 세션 게이팅 `session/index.tsx:236`). "home에 슬롯 렌더"는 슬롯 등록이 아니라 **레이아웃 수술** + 패널 snapshot
  폴이 세션 컨텍스트 의존 → 덜 침습적이 아님.
- **두 옵션(택1, 사용자 결정)**:
  - **A** home 레이아웃 수술: `home.tsx`를 row로 감싸 우측에 autostock 패널+자체 snapshot 폴 마운트(로고/프롬프트 유지).
  - **B(추천·원래 Q1=A 의도)** 부팅 시 세션 라우트 자동 진입(`-c` 최근 세션 or 합성 빈 세션) → **기존 `sidebar_content`
    경로 그대로 재사용**(동작 검증됨), 가시성 `auto&&wide` 유지(BR-7.2).
- 정책 답 후 Code-Gen에서 택1 구현 + 라이브 검증.

## P7 — 런타임 끊김 배너 (E6/BR-8, Q6=B)
- 콘솔이 기존 사이드바 폴 주기(1.5s)에 편승해 `RuntimeHealthSignal` 갱신: snapshot 신선도(P2 동일 기준) +
  `autostock_steer` MCP 가용성(도구 레지스트리에 존재/응답). 끊김 시 사이드바/상단 배너에 사람용 경고(원인+조치,
  **비밀 미포함**). 복구 시 해제. SolidJS 반응형 상태로 구현.

## P8 — 리브랜딩 (BR-14/14.1/14.2, critic #2)
- 로고: `cli/logo.ts` 글리프를 2줄 스택 "auto"/"stock"로(시머 렌더 `logo.tsx:299` 무변경, `marks` 보존, 직사각 유지).
- visible_strings 치환: **provider-id 리터럴 `item.id !== "opencode"` 제외**, **대문자 "OpenCode"/"OC |" 타이틀 포함**.
  치환은 enumerated 위치만(전역 sed 금지).

## 동시성 / 격리
- 런처는 **단명 단일 프로세스**, 동시성은 health-wait 폴 루프(단일 async)뿐 — 신규 데몬 동시성 프리미티브 0.
- 다중 `autostock` 동시 실행 = systemd 단일 인스턴스 + 멱등 start(BR-9.1)로 안전.
- worktree 격리로 개발/롤백.

## 보안 매핑
- SECURITY-03: P4(토큰 비노출). SECURITY-11: BR-10/11(권한분리·주문권한 없음 불변). SECURITY-15: P1(fail-closed).
