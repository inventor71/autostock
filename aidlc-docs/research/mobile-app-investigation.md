# 리서치 노트 — autostock 모바일(안드로이드) 앱: 경로 A(MVP) 심층

> 상태: 조사(investigation). 개발 트랙 아님. 작성 2026-06-08.
> 선행 조사(3-포인트 비교)에 이어, **경로 A = Tailscale + opencode 앱 + 데몬 read 표면**을
> 구체화하고 "어떤 앱 / 데몬 연결 / Claude RC 대비 불편 / autostock 필수 변경"에 답한다.

## 0. 결정적 사실 (코드베이스 확인)

| 사실 | 출처 | 함의 |
|---|---|---|
| `autostock` 런처는 opencode **TUI**를 띄움(`bun run dev`), `serve` 아님 | `operator-console/launcher/cli.ts:67` | 모바일을 위한 **서버 모드(`opencode serve`)는 현재 미사용** → 새로 켜야 함 |
| autostock MCP 서버는 **stdio**(opencode가 subprocess로 spawn) | `operator-console/src/mcp-server.ts:2` | 모바일이 직접 못 붙음. opencode 서버가 같은 호스트에서 spawn해야 함 |
| MCP ↔ 데몬 통신은 **파일드롭**(`STEERING_DIR`) | `mcp-server.ts:28` (`new FileDrop(STEERING_DIR)`) | **데몬과 동일 머신** 강제. 원격 분리 불가 |
| 리치 트레이딩 UI(타임라인/사이드바/thesis/surge)는 **opentui 터미널 렌더 전용** | `packages/tui-trading/`, `feature-plugins/sidebar/autostock.tsx` | 웹 `packages/app`엔 **없음** → 모바일은 기본적으로 "리치 대시보드"가 아님 |
| MCP 도구 ≈ 14개: `steer`, `steer_read`(timeline/account/codebase/…), 주문 취소(MUTATING/confirm) 등 | `mcp-server.ts` | 모바일에서 가능한 것 = **에이전트 대화 + 이 도구 호출** |
| 웹 `packages/app`은 **멀티-서버 picker + 서버 URL/비번 수동 추가 + device-code 로그인** 보유 | `app/src/context/server*.tsx`, `account.ts` | 클라이언트 골격은 이미 있음 |

**한 줄 결론:** 경로 A의 모바일 경험은 **"대화형 operator 콘솔"**(폰에서 에이전트에게 "타임라인 보여줘 / NVDA 주문 다 취소 / TSLA 언락")이지, opentui 비주얼 대시보드가 아니다. 데몬·MCP·파일드롭이 전부 PC에 묶여 있으므로 **서버를 PC에서 띄우고 폰만 그 PC에 도달**시키는 그림이다.

---

## 1. 어떤 안드로이드 앱?

핵심 전제: **어떤 opencode 호환 클라이언트든 `opencode serve`(HTTP)에 붙어 "범용 opencode 에이전트 UI"를 그린다.** 그 누구도 autostock의 opentui 트레이딩 화면을 못 그린다(그건 터미널 전용). 그래서 선택은 "대화/도구 표면을 어떤 껍데기로 볼까"의 문제다.

| 옵션 | 정체 | 장점 | 단점 |
|---|---|---|---|
| **A1. opencode 자체 `packages/app`을 PWA로 (권장)** | 이미 repo에 vendored된 Vite/Solid 웹앱 | 우리 코드라 **완전 커스터마이즈 가능**(나중에 트레이딩 뷰 임베드), `i18n/ko` 존재, device-code 로그인 포함, 설치형 PWA로 홈화면 추가 | PWA 빌드/호스팅 한 번 세팅 필요 |
| A2. [hosenur/portal](https://github.com/hosenur/portal) | 모바일-퍼스트 opencode 웹 UI(인-브라우저 터미널 포함) | 제로 빌드로 즉시 체험, 터미널까지 봄 | 우리 트레이딩용 커스터마이즈 불가, 외부 의존 |
| A3. [opencode-remote-android](https://github.com/giuliastro/opencode-remote-android) / [OpenCode Remote(MWM)](https://mwm.ai/apps/opencode-mobile-app/6757406313) | 네이티브 안드로이드 opencode 클라이언트 | 네이티브 UX, 무료 터널 내장 옵션 | 서드파티 신뢰·보안 검토 필요, 커스터마이즈 불가, 트레이딩 도구는 "에이전트에게 말하기"로만 |

**권장: A1 (opencode `packages/app`을 PWA)** — autostock 브랜딩/트레이딩 뷰로 키워갈 유일한 경로. **즉시 체험만 원하면 A2(portal)** 로 하루 만에 검증 가능.

> 네이티브 앱(Capacitor/Tauri/RN)은 경로 B(풀 UX) 때 고려. 경로 A는 **PWA로 충분**(설치형, 푸시도 웹푸시로 일부 가능).

---

## 2. 이 컴퓨터의 데몬에 어떻게 연결되나

```
[ PC = 데몬 호스트 ]                                  [ 안드로이드 폰 ]
  Python 데몬(agent) ──파일드롭(STEERING_DIR)──┐
                                               │
  opencode serve (:4096) ──stdio spawn──> autostock MCP 서버 ──┘
        ▲   (OPENCODE_SERVER_PASSWORD)
        │  Tailscale tailnet (사설, ACL=내 기기만)
        ▼
  PWA(packages/app) 브라우저 ←──────────────── 폰: http://<pc-tailscale-ip>:4096
```

연결 절차(경로 A):
1. **PC에서 서버 기동**: `opencode serve`를 **데몬과 같은 머신**에서 실행 + `OPENCODE_SERVER_PASSWORD` 설정 + autostock MCP(`mcpServerPath`)와 `STEERING_DIR`을 TUI와 동일하게 wiring(§4 참조).
2. **Tailscale 설치**: PC와 폰 모두 같은 tailnet 가입(무료). 포트 개방·DDNS·SSH 불필요, 외부 노출 0.
3. **폰에서 접속**: PWA(또는 portal)를 열고 서버를 **`http://<pc의 tailscale ip>:4096` + 비번**으로 한 번 추가 → 이후 저장됨.
4. **사용**: 에이전트 대화로 `steer_read`(타임라인/계좌/포지션) 읽기, `steer`로 명령(언락/노트/디렉티브), 주문 취소 등. 모든 쓰기는 데몬의 RiskManager·human-order-gate 뒤에서 처리.

핵심: **MCP(stdio)와 파일드롭은 PC 안에서만** 돈다. tailnet에 노출되는 건 **HTTP 서버(:4096) 하나뿐**.

---

## 3. Claude RC 대비 불편한 점 (정직하게)

| 항목 | Claude RC | 경로 A (opencode + Tailscale) |
|---|---|---|
| **네트워크 도달** | zero-port relay, **아무 설정 없이** 어디서나 | **Tailscale(또는 터널) 필수** — PC/폰에 1회 설치 |
| **자동 detect** | 같은 계정 로그인 → 세션이 목록에 **자동 등장**(녹색 점) | **서버 URL+비번 1회 수동 등록**. 자동 등장 없음(경로 B에서 해결) |
| **페어링** | QR 스캔 즉시 | URL 타이핑(또는 자체 QR 추가) |
| **UI** | 로컬 세션 UI를 그대로 미러 | **에이전트 대화 + MCP 도구**만. opentui 비주얼 대시보드(타임라인/사이드바)는 **안 보임** |
| **푸시 알림** | 내장(앱 푸시) | 기본 없음(웹푸시 직접 구현 필요) |
| **세션 수명** | 끊겨도 자동 재연결, 라이프사이클 매끈 | `opencode serve` 프로세스를 **계속 켜둬야**(systemd로 상시화 권장) |
| **인증** | claude.ai OAuth(짧은 멀티 credential) | 서버 비번 + Tailscale ACL(직접 관리) |
| **설치 마찰** | 앱 깔고 로그인 끝 | 서버 모드 + 터널 + MCP wiring 1회 세팅 |

요약: **편의성은 Claude RC가 확실히 위.** 경로 A의 대가는 "Tailscale 1회 + 수동 서버 등록 + 비주얼 대시보드 대신 대화형"이다. 대신 **autostock 트레이딩 도메인을 그대로**(우리 MCP·RiskManager·human-gate) 쓸 수 있다는 게 Claude RC엔 없는 강점.

---

## 4. autostock에 맞춰 꼭 바꿔야 할 것

1. **서버 모드(`opencode serve`) 경로 추가 (필수).**
   현재 런처(`cli.ts`)는 TUI만 spawn한다. 모바일용으로 `opencode serve`를 **데몬과 같은 환경/같은 MCP·STEERING_DIR wiring**으로 띄우는 진입점이 필요. TUI가 쓰는 `launcher/config.ts`의 `mcpServerPath` + env(STEERING_DIR/STEERING_OPERATOR_TOKEN)를 serve에도 동일 주입해야 MCP가 붙는다. systemd `--user` 유닛으로 상시화 권장(런처가 이미 systemd를 다룸).

2. **MCP가 stdio+파일드롭 = 호스트 고정 (제약 인지).**
   `opencode serve` 인스턴스는 **데몬 호스트에 핀**된다(원격 분리 불가). "이 컴퓨터의 데몬"엔 정확히 맞지만, 멀티-머신/클라우드는 경로 A 범위 밖.

3. **모바일 세션 권한 프로파일 = 안전 기본값 (보안 필수).**
   autostock엔 normal vs supervisor 권한 프로파일(F26/F39)이 있다. 모바일 세션은 **읽기 + 게이트된 steering** 기본, **주문/뮤테이팅 도구는 confirm 강제**(MCP가 이미 `MUTATING, confirm` 표기). human-order-gate·shorting 토글을 모바일이 우회 못 하게 확인.

4. **시크릿/노출 위생.**
   `:4096`을 **절대 공개 인터넷에 열지 말 것**(Tailnet/터널만). `OPENCODE_SERVER_PASSWORD` 필수(미설정 시 서버가 "unsecured" 경고). `STEERING_OPERATOR_TOKEN`은 tailnet 안에서만.

5. **(선택, 경로 A+) 데몬 read 표면 재사용.**
   비주얼 대시보드를 조금이라도 원하면, 이미 데몬이 발행하는 **`steering/health.json`(F69)·타임라인/포지션 기록(JSONL)**을 `packages/app`의 작은 패널로 읽게 하는 게 최소 노력. 풀 트레이딩 뷰(opentui 포팅)는 경로 B/별도 트랙.

6. **트레이딩 비주얼은 포팅 대상임을 명시.**
   타임라인 바·사이드바·thesis 오버레이는 **opentui(터미널) 전용**이라 웹/모바일에서 그대로 안 보인다. 모바일에서 보려면 **웹 컴포넌트로 재구현**해야 함(경로 A MVP 범위 밖, 후속).

---

## 5. 경로 A MVP 권장 순서 (개발 시)

1. `opencode serve` 진입점 + MCP/STEERING wiring + 비번 + systemd 유닛.
2. Tailscale로 폰 도달 확인 → 폰 브라우저에서 portal(A2)로 **즉시 스모크**(에이전트 대화로 steer_read 동작 확인).
3. `packages/app`을 PWA로 빌드·autostock 브랜딩 → 폰 홈화면 설치(A1).
4. 모바일 권한 프로파일 = 안전 기본값 검증(주문 confirm 게이트).
5. (선택) health.json/포지션 read 패널 1개 임베드.

→ 실제 개발 착수 시 `/ai-dlc-request`로 트랙화.

## 참고
- Claude RC: https://code.claude.com/docs/en/remote-control
- opencode 원격 가이드(Tailscale): https://ice-ice-bear.github.io/posts/2026-03-11-opencode-remote/
- portal(모바일 웹 UI): https://github.com/hosenur/portal
- opencode-remote-android: https://github.com/giuliastro/opencode-remote-android
- OpenCode Remote(MWM): https://mwm.ai/apps/opencode-mobile-app/6757406313
- (upstream opencode는 sst → Anomaly로 이전; 본 repo는 b26a930 vendored 스냅샷)
