# F5 NFR Design — Logical Components (유닛 `console-native-launcher`)

## 신규 컴포넌트 (런처/운영 — `operator-console/launcher/`, TS/Bun + 셸)
| 컴포넌트 | 책임 | 패턴 |
|---|---|---|
| `launcher/cli.ts` | 진입 오케스트레이션: resolveConfig→preflight→ensureDaemon→**launchConsole(exec 핸드오프)**; 종료코드 규약; launcher-side watch 없음(critic2 #1); 콘솔 env=AUTOSTOCK_ROOT+STEERING_DIR+token, cwd=`operator-console/cli`(critic2 #2) | P1/P4 |
| `launcher/config.ts` | `LauncherConfig`(E5) 해석: AUTOSTOCK_ROOT/STEERING_DIR/canonical token/mcp path/install path | P4/P5 |
| `launcher/preflight.ts` | `PreflightCheck`(E1) 순수 판정 + 집계(E2) + remediation 텍스트 | P5 |
| `launcher/daemon.ts` | `DaemonService`(E3) systemd 래퍼: ensure_installed/ensure_running/is_active; health-wait(P2) | P2/P3 |
| `launcher/unit-template.ts` | systemd 유닛 텍스트 생성(WorkingDirectory/EnvironmentFile/ExecStart/Restart) | P3 |
| `launcher/install.sh` (or `setup.ts`) | 멱등 설치: `~/.local/bin/autostock` 심 배치 + 유닛 생성/reload/enable/linger + PATH 안내 | P3/BR-15 |
| `~/.local/bin/autostock` (심) | `exec bun {AUTOSTOCK_ROOT}/operator-console/launcher/cli.ts "$@"` | FR-3 |

- **재사용(불변)**: `operator-console/src/filedrop.ts`(snapshot 리더/torn-safe), `schema.ts`(타입). 신규 의존 0.

## 포크 편집 컴포넌트 (`operator-console/cli/packages/opencode/...`)
| 위치 | 변경 | 패턴 |
|---|---|---|
| `src/cli/logo.ts` | `logo`/`go` 글리프 → 2줄 스택 "auto"/"stock"(marks 보존, 직사각) | P8 |
| `cmd/tui/app.tsx:459/466/471/476` | 터미널 타이틀 "OpenCode"/"OC \|" → autostock 표기 | P8(BR-14.2) |
| `feature-plugins/home/tips.tsx`, 기타 visible 표면 | 노출 "opencode"→autostock; **`item.id !== "opencode"` 제외** | P8(BR-14.1) |
| `routes/home.tsx` 또는 부팅 네비 | home-skip 메커니즘 — **옵션 A**(home row 레이아웃+패널) 또는 **옵션 B**(세션 자동 진입, 추천): 정책 분기 (critic2 #5) | P6 |
| `feature-plugins/sidebar/autostock.tsx` (+배너 영역) | `RuntimeHealthSignal` 소비 → 끊김 배너; 가시성 `auto&&wide` 유지 | P7 |

- **provider-id 보존**: `tips.tsx:44`, `sidebar/footer.tsx:12`의 `"opencode"` 비교 리터럴 불변(critic #2).

## 파이썬 / 데몬
- **코드 변경 0 목표.** systemd 유닛이 기존 `main.py --mode agent --steering`를 그대로 기동. 헬스 = 기존
  `runtime.publish_snapshot`이 발행하는 snapshot 신선도(신규 엔드포인트 없음). 토큰 = 기존 root `.env` 경로.

## 데이터 / 파일
- `~/.config/systemd/user/autostock-daemon.service` (생성, 멱등).
- `~/.local/bin/autostock` (심, 생성).
- 읽기: root `.env`(canonical token), `${STEERING_DIR}/snapshot.json`(헬스), `cli/.env`/`.opencode/opencode.jsonc`(drift 검사).
- **쓰기 금지(불변)**: `steering/commands.jsonl` 등 채널 계약 — 런처는 채널을 *읽기*만, 명령은 콘솔 MCP 경로로만.

## 검증 항목 (Code Gen에서 확정/라이브)
1. **health-wait 상수**(window 45s / timeout 60s / poll 1s)를 실제 cold-start(premarket research) 및 executor
   배치 중 false-wedged 안 나는지 라이브 확인(critic #1).
2. **systemd 유닛 WorkingDirectory/EnvironmentFile**로 토큰이 실제 로드되어 콘솔 명령이 먹는지(critic #4 회귀 음성).
3. **home-skip 메커니즘**(옵션 A row-레이아웃 or B 세션 자동 진입) — 사이드바 표시 + 입력/명령 흐름 무파손(critic2 #5).
3b. **콘솔 env/cwd 재현** — `autostock_steer` MCP 등록 확인(token만 아니라 AUTOSTOCK_ROOT/STEERING_DIR + cwd, critic2 #2).
3c. **TTY exec 핸드오프** — 콘솔이 컨트롤링 터미널 정상 확보, 입력 데드/깨짐 없음(critic2 #1).
4. **MCP 경로 해석**(절대/`{env:}`) — `autostock_steer` 로드 확인(메모리 회귀 음성).
5. **토큰 drift warn** — cli/.env 불일치 시 warn 뜨고 주입값으로 명령 먹는지.
6. **리브랜딩** provider-id 보존(connected 정상) + 대문자 타이틀 교체.

## 테스트 전략
- **bun unit**: preflight 판정/집계, 토큰 canonical 해석/drift, 유닛 텍스트 생성(순수 함수). 기존 러너.
- **셸/통합**: install.sh 멱등(재실행 안전), 종료코드 규약(blocking 실패→비-0+진단).
- **파이썬**: 무회귀(기존 pytest, 데몬 코드 0 변경).
- **라이브(사용자 머신)**: `autostock` 한 줄 → 데몬 자동기동 → 사이드바 진입 → 명령 먹힘 + 검증 항목 1–6.

## 보안
- SECURITY-03(P4 토큰 비노출), SECURITY-11(권한분리 불변), SECURITY-15(P1 fail-closed). PBT: 프리플라이트
  판정/토큰 비교 순수 함수에 선택적 example 테스트(대체로 N/A).
