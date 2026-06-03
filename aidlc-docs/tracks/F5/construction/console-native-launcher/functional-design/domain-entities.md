# F5 Functional Design — Domain Entities (유닛 `console-native-launcher`)

> 깊이: light. 안전-크리티컬 도메인(주문/리스크/채널 계약)은 **불변** — 본 유닛은 그 위의
> 진입점/운영/UX 레이어만 모델링한다. 신규 동시성 프리미티브 없음.

## 확정된 FD 결정 (질문 답변, 2026-05-30)
- **Q1=B** — 로고 = **2줄 스택** "auto" / "stock" (기존 블록폰트 스타일 + 시머 유지).
- **Q2=A** — systemd user 서비스 = **`Restart=on-failure` + 부팅/로그인 자동시작(`enable` + linger)**.
- **Q3=A** — 콘솔 TUI 종료 시 **데몬은 계속 실행(detached)**.
- **Q4=A** — `autostock` 설치 = **`~/.local/bin/autostock`** (user 레벨).

---

## E1 — PreflightCheck (프리플라이트 단일 점검)
기동 전 점검 하나의 결과.
- `id`: 식별자 (`token_match` | `steering_dir` | `daemon_health` | `mcp_path`).
- `label`: 사람용 이름.
- `status`: `pass` | `fail` | `skip`.
- `detail`: 사람용 한 줄 진단 (**토큰 값 등 비밀 미포함** — BR-6).
- `remediation`: 실패 시 해결 방법 한 줄 (예: "root `.env`와 `cli/.env`의 STEERING_OPERATOR_TOKEN을 일치시키세요").
- `severity`: `blocking` (실패 시 기동 중단) | `warn` (배너 경고만).

## E2 — PreflightReport (프리플라이트 종합)
- `checks`: `PreflightCheck[]`.
- `ok`: 모든 `blocking` 체크 통과 여부.
- `exit_action`: `proceed` | `abort` (BR-1 fail-closed). `abort` 시 비-0 종료코드 + 진단 출력.

## E3 — DaemonService (트레이딩 데몬 = systemd user 서비스)
`python main.py --mode agent --steering`을 감싸는 운영 서비스 디스크립터.
- `unit_name`: `autostock-daemon.service` (user scope).
- `state`: `active` | `inactive` | `activating` | `failed` | `not-installed`.
- `policy`: `Restart=on-failure`, `enable`+linger (Q2=A).
- 행위:
  - `is_active()` — `systemctl --user is-active`.
  - `ensure_installed()` — 유닛 파일 없으면 생성·`daemon-reload`·`enable`·linger (최초 1회).
  - `ensure_running()` — inactive면 `start` 후 **health-wait**(E4); 이미 active면 no-op (BR-3 중복기동 금지).
- **수명**: 콘솔과 독립(Q3=A). 콘솔 종료가 서비스를 내리지 않음.

## E4 — DaemonHealth (데몬 헬스 신호)
서비스가 active여도 "실제로 살아있나"를 판정.
- 근거: repo-root `steering/snapshot.json`의 신선도(mtime within `health_window`초) — 데몬이 주기 발행.
- `healthy`: bool. `last_publish_age`: 초.
- active이지만 stale → `wedged` 진단 (BR-2): 서비스는 떴는데 발행이 멈춤.

## E5 — LauncherConfig (런처가 해석한 실행 컨텍스트)
`autostock` 런처가 콘솔 기동 전에 확정하는 환경.
- `autostock_root`: repo 루트 (AUTOSTOCK_ROOT).
- `steering_dir`: `${autostock_root}/steering`.
- `daemon_token` / `console_token`: root `.env` / `cli/.env`(또는 `.opencode`)에서 읽은 토큰 — **메모리에만**,
  로그/출력 금지 (BR-6). 토큰 **일치 여부(boolean)** 만 산출.
- `mcp_server_path`: `${autostock_root}/operator-console/src/mcp-server.ts` (절대경로 해석).
- `install_path`: `~/.local/bin/autostock`.

## E6 — RuntimeHealthSignal (런타임 끊김 감지, Q6=B)
기동 후 콘솔이 주기적으로 갱신하는 연결 상태.
- `channel_ok`: snapshot/events 갱신되는가.
- `mcp_ok`: `autostock_steer` MCP 로드/응답하는가.
- 변화 시 사이드바/상단 **배너**로 표면화 (조용한 반-기동 방지).

## E7 — BrandSurface (리브랜딩 표면 인벤토리, FR-2)
교체 대상의 분류(엔티티라기보단 작업 인벤토리; BLM/BR에서 참조).
- `logo_glyphs`: `cli/logo.ts` (`logo`/`go`) — 2줄 스택 "auto"/"stock"로 교체.
- `visible_strings`: 푸터/스플래시/창(터미널) 타이틀/팁/about 등 사용자 노출 "opencode".
- **비대상**: 내부 패키지명/import 경로/식별자 (§비범위).

## 메인(F4) 재사용 경계 (변경 없음)
- `steering/` 파일드롭 계약(commands/events/snapshot/.cursor) + Unit A 데몬 엔진 + RiskManager→Broker 게이트.
- 콘솔의 NL→MCP `autostock_steer` 경로 + 기존 `src/filedrop.ts`(snapshot 읽기·토큰 env) — 프리플라이트가 재사용.
- opencode 포크의 사이드바(`autostock.tsx` `sidebar_content()`), 키맵(`<leader>b`), 락다운(`AUTOSTOCK_LOCKDOWN`).
