# F71 — 요구사항 분석 (모바일 operator, 경로 A)

> Depth: **Standard**. Brownfield. 베이스 = pre-inception Q&A 3라운드 확정(`state.md` Scope) +
> 조사 노트 `aidlc-docs/research/mobile-app-investigation.md`. 승인 게이트 전 다음 단계 진행 금지.

## 1. 의도 (Intent)

autostock 운영자가 **폰에서** 실행 중인 트레이딩 데몬을 모니터링·조종할 수 있게 한다. Claude
Remote Control과 같은 매끄러움은 아니되(zero-port relay·자동detect 없음), autostock 도메인(우리
MCP·RiskManager·human-order-gate)을 그대로 쓰는 **대화형 operator + 읽기 패널**을 제공한다.

**경로 A**: PC(데몬 호스트)에서 `opencode serve`(systemd 상시) → 폰이 **Tailscale**로 도달 →
**PWA(`packages/app`)**. 모바일은 데몬 호스트에 핀된다(MCP=stdio+파일드롭).

## 2. 기능 요구사항 (FR)

- **FR-1 (서버 모드).** `opencode serve`를 **TUI와 동일한 MCP(`mcpServerPath`)·`STEERING_DIR`·
  토큰 env wiring**으로 기동하는 진입점을 제공한다. 폰 클라이언트가 이 서버에 붙어 autostock MCP
  도구를 쓸 수 있어야 한다. (검증: 폰에서 `steer_read` 호출 성공.)
- **FR-2 (상시 가동).** 위 서버를 **systemd --user 유닛**으로 상시 가동(런처가 이미 systemd 관리).
  데몬과 수명 정렬, 부팅 시 자동 기동.
- **FR-3 (네트워크 도달).** 폰은 **Tailscale tailnet**으로 서버(`:4096`)에 도달. `:4096`은 공개
  인터넷에 절대 노출하지 않는다(tailnet 한정).
- **FR-4 (수동 서버 등록 + QR).** 폰 PWA는 서버를 **URL+비번으로 1회 등록**(이후 저장). PC가
  **QR(tailscale URL+비번)** 을 표시해 폰 스캔으로 등록을 편의화한다. (계정기반 자동detect는 범위 밖.)
- **FR-5 (대화형 operator — 기본).** 폰에서 opencode 에이전트와 대화하며 autostock MCP 도구를
  호출: `steer_read`(읽기), `steer`(언락/노트/디렉티브/answer), 주문 취소/포지션 청산/긴급정지.
- **FR-6 (읽기 대시보드 패널).** `steer_read` 호출을 감싼 패널 UI로 health.json(F69)·포지션·계좌
  요약을 **대화 없이 한눈에** 표시. (데이터 경로 = MCP, 데몬 JSON 직배 아님.)
- **FR-7 (추론 트레이스 뷰어).** research/intraday/eod 턴의 논지·결정·근거를 폰에서 읽기(steer_read 기반).
- **FR-8 (뮤테이팅 confirm = WebAuthn).** 주문 취소/포지션 청산/긴급정지 등 **뮤테이팅 도구는
  WebAuthn 패스키 서명**을 통과해야 실행. 폰에 패스키 1회 등록 → 매 뮤테이팅마다 지문/Face 서명.
- **FR-9 (제어 범위 한정).** 모바일이 호출 가능한 뮤테이팅은 **기존 MCP 도구(취소/청산/긴급+steering)**
  뿐. **신규 수동 주문 진입(새 매수/매도 작성)은 범위 밖**(에이전트가 냄).
  **긴급정지 포함 모든 뮤테이팅에 서명 요구(예외 없음)** — 일관성 우선(UAQ 2026-06-11).
- **FR-10 (TUI 세션 이어보기 — feasibility 게이트).** PC TUI에서 하던 에이전트 대화를 폰에서
  열람/이어가기를 **시도**한다. Application Design에서 serve↔TUI 세션 저장소 공유 여부를 검증해
  가능하면 구현, 불가하면 **'별도 대화 + 데몬 상태 공유' fallback**으로 확정(스코프 다운그레이드는
  사용자 보고 후). 홈 화면은 **대시보드 우선**, QR은 **URL+비번 포함**(동일 UAQ).

## 3. 비기능 요구사항 (NFR — 초안, Construction NFR서 정련)

- **NFR-1 (보안 — 최우선, Security Baseline).**
  - `OPENCODE_SERVER_PASSWORD` 필수(미설정 시 unsecured 경고). `:4096` tailnet 한정.
  - 뮤테이팅 = WebAuthn 패스키(클라이언트 게이트) **+ 서버측 human-order-gate·RiskManager**(방어 심층, 우회 불가).
  - 시크릿(`STEERING_OPERATOR_TOKEN`) tailnet 외 노출 금지, 저장물에 평문 미포함.
  - 모바일 세션 권한 프로파일 = **안전 기본값**(읽기+게이트 steering; 뮤테이팅은 confirm 필수).
- **NFR-2 (프로덕션 무영향).** serve/PWA 미사용 시 데몬·TUI 동작 불변. 서버는 추가 표면일 뿐
  기존 트레이딩 경로를 바꾸지 않는다.
- **NFR-3 (가용성).** systemd 상시 + 재시작. 데몬 호스트에 핀(원격 분리 비목표).
- **NFR-4 (사용성).** 등록 1회 후 재접속 마찰 최소. 패널은 대화 없이 핵심 상태 노출. tailnet 끊기면
  명확한 오프라인 표시.

## 4. 범위 밖 (Out of Scope)

- 계정기반 **자동detect**(로그인→세션 자동 등장) — 경로 B 후속.
- **푸시 알림** — MVP 제외(후속).
- **신규 수동 주문 진입**(폰에서 새 주문 작성).
- opentui **비주얼 대시보드 전체 포팅**(타임라인 바/사이드바 z-order 등) — 후속.
- off-host/클라우드 분리(멀티 머신), 실거래(live) 전용 기능.
- iOS 네이티브, 앱스토어 배포(PWA로 충분; Capacitor 네이티브는 후속).

## 5. 가정 / 의존 (Q&A 검증 완료)

- A1. PWA WebAuthn = 패스키 ceremony(등록 1회) — 수용됨. **서버측 WebAuthn 등록/검증 엔드포인트 신규 필요**.
- A2. "주문까지" = 취소/청산/긴급(기존 MCP), 신규 작성 아님.
- A3. 읽기 데이터 경로 = MCP(steer_read) 패널 래핑.
- A4. `opencode serve`는 MCP(stdio)+파일드롭 때문에 **데몬 호스트 핀** — "이 컴퓨터" 전제와 일치.
- A5. `packages/app`은 vendored 우리 코드라 패널/브랜딩/WebAuthn 추가 가능(SolidJS 프론트 작업량 有).

## 6. 미해결 → Application Design/NFR서 확정

- **WebAuthn 서버측 구현 위치**: `opencode serve`에 라우트 추가 vs autostock MCP 측 게이트.
- **권한 프로파일 적용 지점**: opencode permission(F26) vs MCP 도구 confirm vs 둘 다.
- **QR 표시 주체**: serve 기동 로그 vs 런처 서브커맨드.
- **패널 데이터 폴링 주기/캐시**(NFR-4 vs 부하).
- **operator-console/cli(opencode) 변경 = 서브모듈/포크 영역** → 머지 시 fork main 반영 경로 확인.

## 7. Extension (state.md 확정 반영)

- **Security Baseline: Enabled (Applicable)** — §3 NFR-1 전반. trade-affecting + 네트워크 노출이라 핵심.
- **Property-Based Testing: Partial 예상** — 순수 로직(예: confirm 게이트 판정/권한 결정)에 한정,
  UI/통합은 비대상. NFR 단계서 N/A vs Partial 최종.

## 8. 영향 코드(예상) — Application Design서 확정

- `operator-console/cli/packages/opencode` — `serve` 기동 래핑 + (가능 시) WebAuthn 라우트.
- `operator-console/cli/packages/app` — autostock 패널(대시보드/트레이스), WebAuthn confirm, QR 등록.
- `operator-console/launcher/` — `serve` 서브커맨드 + systemd 유닛 + MCP/STEERING env wiring.
- `operator-console/src/mcp-server.ts` — 뮤테이팅 도구에 confirm/권한 메타(이미 MUTATING 표기) 강화.
- 데몬측 변경 최소(읽기는 기존 steering/health.json·기록 재사용).
