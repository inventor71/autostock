# F86 — Application Design (consolidated)

> 트랙 F86. 신규 read-only 서버 엔드포인트 + 클라 폴링 배선. 본 문서는
> `components.md` / `component-methods.md` / `services.md` / `component-dependency.md`를 요약·통합한다.

## 0. 설계 결정 — 열린 질문 해소 (OQ-1~3)

코드 조사로 확정(별도 사용자 질문 불요 — 큰 제품 결정은 Requirements UAQ에서 이미 확정, 아래는 기존 발행
데이터에 근거한 기술 결정):

| OQ | 결정 | 근거 (코드) |
|---|---|---|
| **OQ-1 데이터 소스 메커니즘** | **steering/*.json 직접 파일 read** (MCP 경유 아님) | 콘솔은 이미 steering 디렉터리를 파일로 접근(`scripts/verify.sh` read-allowlist `../../steering/**`, `STEERING_DIR` env). MCP `autostock_steer_read`는 에이전트 도구 채널 — HTTP 데이터 API엔 부적합. |
| **OQ-1b STEERING_DIR 해석** | `process.env.STEERING_DIR` → 없으면 `AUTOSTOCK_ROOT/steering` → 없으면 콘솔 cwd 기준 `../../steering` (repo-root/steering) | 데몬 기본 `DEFAULT_STEERING_DIR=<repo>/steering`; verify 컨테이너는 `STEERING_DIR=/app/steering`, consoleCwd=`/app/operator-console/cli`. 셋 다 실패 시 fail-safe(빈/stale). |
| **OQ-2 market phase 소스** | `monitor.json`의 `market`(F25 market-aware 규칙) + `snapshot.json`의 `market_open` 폴백 → 클라가 `DashboardView` phase로 매핑 | `publish_monitor`가 `"market": self._market_rule`, `"session_et_date"` 발행. TUI 타임라인이 쓰는 권위 소스 — 신규 ET 로직 불요. |
| **OQ-3 agent activity 소스** | `monitor.json`의 `current_turn`(→ `agent.current`) + `decisions`(구조화 tail → `agent.recent[]`) | `publish_monitor`가 `current_turn`·구조화 `decisions`(_decisions_tail, action/symbol/turn_id 상관)를 발행. |

### 0.1 발견된 계약 갭 (정직성 — Functional Design에서 확정)
- `_account_block` 발행 필드 = `{equity, cash, invested, open_pnl, position_count}`.
  **`day_pnl_pct`·`buying_power`는 현재 미발행** → F79 `DashboardModel.dayPnlPct` / `DashboardView.buyingPower`가 기대.
  - **v1 정직 처리**: 미발행 필드는 **null** (거짓값 합성 금지). `equity`/`cash`/`position_count`/`open_pnl`는 실값.
  - **선택적 소폭 보강(데몬, 별도 판단)**: `day_pnl_pct`를 `equity_log`(전일 종가 기준)에서 산출해 account block에
    추가하면 "한눈 일손익"이 채워짐. **이번 트랙 기본 범위 밖**(read-only 원칙) — 사용자가 원하면 포함. Functional
    Design 승인 시 결정.

## 1. 컴포넌트 개요

| ID | 컴포넌트 | 위치 | 책임 | 순수성 |
|---|---|---|---|---|
| **C1** | `DashboardReadRoute` | `opencode/src/server/autostock/dashboard-read.ts` (신규) | `GET /autostock/dashboard` 처리: steering dir 해석 → 파일 read → C3 조립 → JSON 응답. server.ts에 마운트 1줄. | I/O 경계 (얇음) |
| **C2** | `SteeringDirResolver` | C1 모듈 내 pure fn | env/cwd로 steering 디렉터리 경로 결정 (OQ-1b). 미해석 시 null → fail-safe. | 순수 |
| **C3** | `assembleDashboardPayload` | C1 모듈 내 pure fn (또는 `dashboard-read-core.ts`) | 읽은 steering JSON(snapshot/health/monitor/pending) → 대시보드 응답 객체. **never-throw, 부분-정직**(누락→null/empty). PBT 핵심. | 순수 |
| **C4** | `DashboardPoller` (클라 배선) | `app/src/addons/autostock/mobile-shell.tsx` (+ 작은 `dashboard-source.ts`) | `/autostock/dashboard` 폴(~5s, background/locked 시 중단) → `assembleSnapshot`→`toDashboard`→`DashboardView`. `isStale`로 stale prop. | I/O 경계 + 기존 순수 코어 |
| (재사용) | `assembleSnapshot`/`toDashboard`/`isStale`/`DashboardView` | `app/src/addons/autostock/{snapshot.ts,dashboard.ts,dashboard-view.tsx}` (F79) | **무변경 지향**. C3 응답이 `assembleSnapshot` 입력 형태와 정합하면 클라 코어 그대로. | 순수 (기존) |

> **핵심 설계 원칙**: 동작-critical 로직은 **순수 코어(C2/C3 서버, F79 클라 코어)** 에 두고 단위/PBT로 검증.
> C1/C4는 얇은 I/O 배선. webauthn.ts와 동일한 fork-isolated 스타일(rebase 표면 최소화).

## 2. 데이터 소스 매핑 (steering 파일 → 응답 계약)

| 응답 필드 | 소스 파일 · 키 | 비고 |
|---|---|---|
| `account.equity` | snapshot.json `account.equity` | 실값 |
| `account.cash` | snapshot.json `account.cash` | 실값 |
| `account.day_pnl_pct` | (미발행) | **null** (v1). 옵션: equity_log 보강 |
| `account.buying_power` | (미발행) | **null** (v1) |
| `account.open_pnl`, `position_count` | snapshot.json `account.*` | 실값 (보조 표시) |
| `positions[]` | snapshot.json `positions{}` (symbol→{qty,avg_entry_price,side,current_price,market_value,unrealized_pnl}) | dict→array 변환. `unrealized_pnl`→행 P&L |
| `health` | health.json `{status\|ok}` | 없으면 null=unknown |
| `pending_approvals` | pending_approvals.json (개수) 또는 snapshot `pending` 길이 | 대시보드 카운트용. 라이브 승인 시트는 별도(이벤트 구동, 무변경) |
| `market` | monitor.json `market` + snapshot `market_open` 폴백 | 클라가 phase(pre/regular/after/closed)로 매핑 |
| `agent.current` | monitor.json `current_turn` | in-flight 턴 |
| `agent.recent[]` | monitor.json `decisions` (tail) | action/symbol/summary/ts |
| `published_at` | snapshot.json mtime 또는 monitor `ts` | **staleness 판정 필수**(NFR-2). 없으면 stale |

## 3. 서비스/오케스트레이션 (요약 — services.md 참조)

- **서버 read 서비스**: 요청 → `SteeringDirResolver` → 각 파일 best-effort read(try/catch per file) →
  `assembleDashboardPayload` → 200 + JSON. 어떤 파일 부재/파싱실패도 **부분 응답**으로 흡수(절대 5xx 아님, NFR-3).
  인증은 기존 basic-auth + tailscale 경계(라우트는 그 뒤에 마운트, read-only).
- **클라 폴 서비스**: `onMount` 1회 + `setInterval(POLL_MS)` refetch; `document.hidden`/`locked()` 시 스킵;
  `onRefresh`(탭) 즉시 refetch; `onCleanup`에서 interval 해제. 결과 → 기존 코어 → DashboardView.

## 4. 컴포넌트 의존 (요약 — component-dependency.md 참조)

```
[Phone PWA]
   │  GET /autostock/dashboard  (basic-auth + tailscale TLS, ~5s poll)
   ▼
C1 DashboardReadRoute ──uses──▶ C2 SteeringDirResolver
   │                         └─▶ C3 assembleDashboardPayload
   │  reads (fs, read-only)
   ▼
<STEERING_DIR>/{snapshot.json, health.json, monitor.json, pending_approvals.json}
   ▲  (written by python daemon SteeringRuntime — UNCHANGED)

[Phone PWA]  C4 DashboardPoller ──▶ assembleSnapshot ─▶ toDashboard ─▶ DashboardView
                                   └─▶ isStale ─▶ stale 배지
```
- **신규 경계 1개**: 응답 JSON 계약(C3 생산 ↔ C4 소비). python 데몬 발행 스키마는 read-only 의존(무변경).
- **공유 파일**: `server/server.ts`(마운트 1줄), `mobile-shell.tsx`(배선). F84(차트)가 동일 데이터 의존 — 인접.

## 5. 보안/품질 반영 (설계 단계)

- **SECURITY-05/입력검증**: 라우트는 고정 파일명만 read(사용자 입력→경로 결합 없음) → path traversal 불가. 쿼리파라미터 미사용(또는 무시).
- **SECURITY-08/접근제어**: read 라우트는 기존 인증 경계 뒤(deny-by-default). read-only — mutating 게이트 무관. CORS 와일드카드 미도입.
- **SECURITY-15/fail-safe**: 모든 파일 I/O try/catch, 에러→부분/빈 페이로드 + published_at 없음=stale(거짓 신선 금지). 서버 5xx로 셸 미파괴.
- **SECURITY-09/에러노출**: 응답에 스택/내부경로 미포함.
- **PBT-01 속성(클라/서버 코어)**: ① C3 never-throw(임의 부분/깨진 입력→유효 부분 페이로드) ② staleness fail-safe(`isStale` 항상 보수적) ③ positions dict→array 보존(크기/심볼). 상세는 Functional Design.

## 6. 범위 밖 (재확인)
portfolio history/자산곡선(F84), 세션입력 클라서명, SSE/푸시, 데몬 신규 발행물 추가(day_pnl 보강은 옵션 결정 사항).
