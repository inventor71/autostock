# F86 — 모바일 대시보드 데이터 엔드포인트 · Requirements

> 트랙: **F86** · 유형: feature (brownfield, monorepo) · 깊이: Standard
> F79 후속 — PWA `/autostock` 대시보드 실데이터 배선.

## 1. Intent Analysis (의도 분석)

| 항목 | 값 |
|---|---|
| **User Request** | "모바일 대시보드 데이터 엔드포인트" (`/ai-dlc-request`) |
| **Request Type** | Enhancement / New Feature — F79가 남긴 명시적 fast-follow |
| **Scope Estimate** | Multiple Components — opencode serve 서버(node) + PWA addon(SolidJS); 데이터는 python 데몬 산출물(파일) |
| **Complexity** | Moderate — 신규 read 라우트 1개 + 데이터 계약 + 클라 폴링 배선. 보안 경계(원격 노출)·staleness가 핵심 고려 |
| **Clarity** | Clear (4개 UAQ로 전송/인증/범위/확장 확정) |

### 배경 (현 상태)
- **F79가 이미 만든 것**: 모바일 셸 `/autostock`(`mobile-shell.tsx`), 승인 시트, 잠금,
  그리고 **클라 대시보드 코어** — `dashboard.ts`(`toDashboard`/`DashboardModel`),
  `snapshot.ts`(`assembleSnapshot`/`buildDashboard`/`isStale`), `dashboard-view.tsx`(`DashboardView`,
  종목별 P&L 행·시장 세션·에이전트 활동·현금/매수여력 렌더 지원).
- **빠진 것 (이 트랙)**: serve 서버에 autostock **read 엔드포인트**가 없어 `mobile-shell`이
  `EMPTY_MODEL`을 렌더하고 "실시간 데이터 연결은 후속" 고지를 띄운다.
- **데이터는 이미 발행됨**: 데몬의 `SteeringRuntime.publish_snapshot()`이 `steering/snapshot.json`
  (account 블록·positions[side/qty/avg/current/market_value/unrealized_pnl]·open_orders·pending·
  market_open·run_state·fills)을 ~5s 주기로 atomic write. `health.json`, `pending_approvals.json`,
  `monitor.json`도 같은 `steering/` 디렉터리(`DEFAULT_STEERING_DIR = <repo>/steering`).
- serve 서버는 데몬과 **동일 호스트** 동작이며 autostock 라우트를 `server/autostock/webauthn.ts`
  (`server.ts`의 `m.route(request)`)로 fork-isolated 마운트한다 → read 라우트의 자연스러운 마운트 지점.

## 2. 확정된 설계 결정 (UAQ, 2026-06-14)

| # | 결정 | 선택 | 근거 |
|---|---|---|---|
| D1 | **전송 방식** | **폴링 GET** — `GET /autostock/dashboard`, 클라 ~5s `setInterval` refetch | 데몬 publish 주기(5s)와 정합, F79 `assembleSnapshot`/`isStale` 코어 그대로 사용, SSE 수명관리 복잡도 회피 |
| D2 | **read 인증** | **basic-auth + tailscale TLS만** (패스키 서명 면제) | read=비-mutating. `webauthn.ts`의 `READONLY_AUTOSTOCK_KEYS`가 이미 `steer_read`/`get_account_info` 등을 서명 면제 → 동일 정책 |
| D3 | **v1 데이터 범위** | account / positions(P&L) / health / pending / market session / agent recent activity | "한눈 확인" 핵심 패널. **portfolio history(자산 곡선) 제외 → F84(모바일 차트)로** |
| D4 | **확장 규칙** | Security Baseline ✅ + Property-Based Testing ✅(full) | 원격 노출 + 잔고/포지션 데이터 → 보안 블로킹; 순수 변환(JSON→모델) → PBT 적합 |

## 3. Functional Requirements

- **FR-1 (read 라우트)**: serve 서버는 `GET /autostock/dashboard`를 제공한다. 응답은 데몬이 발행한
  steering 산출물에서 조립한 **단일 대시보드 스냅샷 JSON**이다. 라우트는 `webauthn.ts`와 동형으로
  fork-isolated(별도 모듈, server.ts에 마운트 1줄)으로 추가한다.
- **FR-2 (데이터 계약)**: 응답 payload는 클라의 기존 `assembleSnapshot`/`toDashboard`가 소비하는 형태와
  정합해야 한다. 최소 필드:
  - `account`: `equity`, `day_pnl_pct`, `cash`, `buying_power`
  - `positions[]`: `symbol`, `market_value`, `unrealized_pnl`(→ dayPct 매핑), `side`, (가능 시 weight)
  - `health`: `{ status | ok }`
  - `pending_approvals`: 개수(또는 배열)
  - `market`: `{ phase: pre|regular|after|closed, label?, nextLabel? }` (또는 `market_open` → 클라 파생)
  - `agent`: `{ current?, recent[]:{ts,action,symbol,summary} }` (가용 소스에서 best-effort)
  - `published_at`: ISO 타임스탬프 (staleness 판정용, NFR-2)
- **FR-3 (graceful/honest 데이터)**: 일부 소스 파일이 없거나(데몬 워밍업) 깨졌을 때 응답은 **부분-정직 모델**
  (해당 필드 null/empty)로 200 반환하되, **누락을 신선함으로 위장하지 않는다**(`published_at` 없으면 stale).
  서버 내부 에러는 fail-safe하게 빈/부분 스냅샷 + stale 신호로 귀결(절대 5xx로 셸을 깨지 않음, NFR-3).
- **FR-4 (클라 배선)**: `mobile-shell.tsx`가 진입 시 + ~5s 주기로 read 라우트를 폴링 → `assembleSnapshot`
  → `toDashboard` → `DashboardView`에 실모델 전달. `EMPTY_MODEL` 고정 + "데이터 연결 후속" 고지 제거.
  `onRefresh` 탭은 즉시 refetch. 폴링은 PWA가 background/locked일 때 중단(불필요 트래픽·NFR-4).
- **FR-5 (staleness 표시)**: 클라는 `isStale(model, now, threshold)`로 신선도를 판정해 DashboardView의
  `stale` prop을 구동(오래된 데이터 시각 배지). threshold는 합리적 기본(예: 30s) — 튜닝 노브.
- **FR-6 (read-only)**: 이 엔드포인트는 어떤 거래/주문/상태도 변경하지 않는다(순수 read). mutating 경로
  (승인·프롬프트)는 F79/F75 게이트 그대로, 무영향.

## 4. Non-Functional Requirements

- **NFR-1 (무영향/추가형)**: `/autostock` 외 라우트·데스크톱 TUI·데몬 흐름 불변. 신규 라우트는 추가형.
- **NFR-2 (신선도/정직)**: 항상 `published_at` 동반, 누락/파싱불가/오프라인은 **fail-safe로 stale 처리**
  (SECURITY-15). 오래된 스냅샷을 신선으로 보고하지 않는다.
- **NFR-3 (회복탄력성)**: 파일 부재·부분쓰기·JSON 파싱 실패에 셸이 깨지지 않음. 서버는 부분/빈 스냅샷 반환,
  클라 `toDashboard`는 never-throw(D-AD-2 보존).
- **NFR-4 (효율)**: 폴링은 가벼운 파일 read만(브로커 호출 없음 — 데몬이 이미 캐시 발행). background/locked
  시 폴 중단.
- **NFR-5 (성능)**: read 라우트 p95 응답은 로컬 파일 read 수준(수 ms). 폴 주기 5s ≪ 데몬 publish 5s 정합.
- **NFR-6 (보안 노출)**: 라우트는 원격(폰/tailscale) 노출 — §6 보안 요건 적용.

## 5. Out of Scope (이 트랙)

- **Portfolio history / 자산 곡선 시계열 + 결정 마커** → **F84**(모바일 차트).
- **세션 입력(프롬프트) 클라 서명 + 세션뷰 모바일 통합** → 별도 후속(F79 post-merge 고지).
- SSE/푸시 실시간 스트림, PWA 오프라인 캐시, 신규 수동 주문 — 범위 밖.
- 데몬 측 신규 산출물 추가(예: 별도 agent-activity 파일) — 기존 발행물로 충족 안 되는 필드는 best-effort
  null. (필요 시 후속 트랙에서 데몬 발행 보강.)

## 6. Security Compliance (Security Baseline — 적용 평가)

> 본 트랙에 **관련된** 규칙만 enforce. 적용 시점은 Application Design / Code Generation / Build & Test.

| Rule | 적용성 | 요건 / N/A 근거 |
|---|---|---|
| SECURITY-04 (HTTP 보안 헤더) | **적용** | HTML 서빙은 기존 PWA 셸. read 라우트는 JSON API — CSP/HSTS 등은 기존 serve 미들웨어 정책 따름. 신규 라우트가 헤더 정책을 약화시키지 않을 것 |
| SECURITY-05 (입력 검증) | **적용** | GET 쿼리/경로 파라미터 최소화·검증. 사용자 입력을 파일경로로 연결하지 않음(고정 steering 파일명만) — path traversal 차단 |
| SECURITY-08 (앱 접근제어) | **적용(핵심)** | read 라우트는 기존 basic-auth + tailscale 경계 뒤. 비인증 원격 접근 거부(deny-by-default). CORS 와일드카드 금지 |
| SECURITY-09 (오설정/에러 노출) | **적용** | 에러 응답에 스택트레이스·내부 경로 미노출. 부분 스냅샷은 일반화된 형태 |
| SECURITY-13 (역직렬화 안전) | **적용** | steering JSON은 데몬(신뢰 호스트)이 생성하지만, 파싱 실패를 안전 처리(allowlist 필드, 예외→부분모델) |
| SECURITY-15 (예외/fail-safe) | **적용(핵심)** | 모든 파일 I/O try/catch, **fail-closed/fail-safe**: 에러 시 stale·부분 스냅샷(거짓 신선 금지), 셸 미파괴 |
| SECURITY-03 (앱 로깅) | **적용(경량)** | read 라우트 접근/에러는 기존 serve 로깅 활용. 잔고/토큰 등 민감정보 로그 미기록 |
| SECURITY-01/02/06/07/10/11/12/14 | **N/A 또는 기존충족** | 신규 데이터스토어·LB·IAM·네트워크 인프라·인증서버·공급망 변경 없음(인증은 F71/F75 기존 자산 재사용). 비밀키/하드코딩 자격증명 신규 도입 없음 |

**블로킹 평가**: 현재 미해결 블로킹 보안 발견 없음. 설계/코드 단계에서 SECURITY-05/08/15 검증을 게이트로 재확인.

## 7. PBT Compliance (Property-Based Testing — full)

> 프레임워크: **fast-check**(F79가 이미 devDependency 도입). 식별된 핵심 속성:

- **Round-trip/변환 정직성 (PBT-02/03)**: `assembleSnapshot`/`toDashboard`는 **never-throw 전역 불변** —
  임의(부분/누락/타입오염) 입력에 대해 예외 없이 `DashboardModel` 반환. 누락 필드 → null/0/empty(거짓 데이터
  생성 금지).
- **Staleness 불변 (PBT-03)**: `isStale`는 offline·`asOf` 없음·파싱불가·임계초과에서 **항상 true**
  (fail-safe). 신선 입력만 false. → 보안 NFR-2와 직접 연결.
- **서버 스냅샷 조립 불변**: read 라우트의 파일→payload 변환이 임의 부분/깨진 파일 입력에서 유효 스키마
  (또는 명시적 부분)만 산출, 예외 미전파.
- **생성기 품질 (PBT-07)**: 도메인 생성기(account/position/health/pending 부분형) — 원시 타입 단독 금지.
- **보완 전략 (PBT-10)**: 핵심 시나리오(정상 풀 스냅샷, 워밍업 빈 스냅샷, 깨진 파일)는 example-based 테스트로
  고정 + PBT로 일반 불변 커버.

상세 속성 식별은 Functional Design(PBT-01)에서 컴포넌트별로 문서화.

## 8. 열린 설계 질문 (→ Application Design에서 확정)

- **OQ-1 (데이터 소스 메커니즘)**: read 라우트가 ⓐ `steering/*.json`을 **직접 파일 read**(동일 호스트,
  STEERING_DIR 해석 필요) vs ⓑ 기존 `autostock_steer_read` 도구 경로 재사용. **leaning = ⓐ 직접 read**
  (단순·데몬 발행물 그대로). STEERING_DIR 해석 방법(env `STEERING_*` vs repo-root 상대) 확정 필요.
- **OQ-2 (market session 파생)**: `snapshot.json`의 `market_open`(bool)만으로 `phase` 4값(pre/regular/
  after/closed)을 충분히 파생 가능한지, 아니면 ET 시계 기반 파생(클라/서버 어디서)인지.
- **OQ-3 (agent recent activity 소스)**: `decisions.jsonl`/`turns.jsonl`/`monitor.json` 중 어떤 발행물에서
  최근 활동을 끌어올지 + 노출 한도.

## 9. 요약 (핵심 요건)

F86은 **serve 서버에 read-only `GET /autostock/dashboard` 라우트**를 추가해 데몬의 steering 발행물을
모바일 대시보드 모델로 공급하고, `mobile-shell`을 5s 폴링으로 배선해 F79가 남긴 빈-모델 화면을 실데이터로
채운다. 전송=폴링 GET, 인증=basic-auth+tailscale, 범위=코어 패널(history는 F84). 보안(원격 노출·fail-safe
신선도)과 PBT(never-throw/staleness 불변)가 품질 게이트.
