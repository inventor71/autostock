# F86 — Business Rules (unit: dashboard-endpoint)

## 서버 (C2/C3) 규칙

- **BR-1 (steering dir 해석)**: `STEERING_DIR` env → `AUTOSTOCK_ROOT/steering` → `cwd/../../steering` 순으로
  첫 번째 **존재하는** 디렉터리. 전부 실패 → null.
- **BR-2 (best-effort read)**: 각 steering 파일은 독립 try/catch. 부재/파싱실패 → 해당 소스 undefined(다른 소스에 무영향).
- **BR-3 (never-throw 조립)**: `assembleDashboardPayload`는 어떤 입력(부분/타입오염/null)에도 예외를 던지지 않고
  유효 스키마의 부분 페이로드를 반환. 숫자 검증 = 유한수만 통과, 아니면 null.
- **BR-4 (미발행 = null)**: `day_pnl_pct`, `buying_power`는 v1에서 항상 null(거짓값 합성 금지).
- **BR-5 (positions 변환)**: snapshot `positions{}`(dict) → array. 각 행 `return_pct`:
  - long: `(current_price - avg_entry_price) / avg_entry_price * 100`
  - short: `(avg_entry_price - current_price) / avg_entry_price * 100`
  - `avg_entry_price`가 0/누락/비유한 → `return_pct = null`.
- **BR-6 (published_at)**: `monitor.ts` 우선, 없으면 snapshot 파일 mtime(ISO), 둘 다 없으면 null.
- **BR-7 (market)**: `monitor.market`에서 phase/label 파생; 없으면 `snapshot.market_open`(bool)만 `{open}`로.
  파생 불가 → null.
- **BR-8 (pending 카운트)**: `pending_approvals.json` 배열 길이; 없으면 snapshot `pending` 길이; 둘 다 없으면 0.
- **BR-9 (fail-safe 응답)**: 전역 try/catch — 어떤 내부 오류도 200 + (빈/부분) payload로 귀결. 5xx·스택트레이스 노출 금지.
- **BR-10 (read-only/경로 안전)**: 고정 파일명만 read. 요청 쿼리/경로를 파일 경로에 결합하지 않음(traversal 불가).

## 클라 (C4) 규칙

- **BR-11 (폴 라이프사이클)**: `onMount` 1회 fetch + `setInterval(POLL_MS=5000)`. 매 tick에서
  `document.hidden || locked()`면 fetch 스킵. `onCleanup`에서 interval 해제.
- **BR-12 (수동 새로고침)**: `onRefresh`(DashboardView 탭) → 즉시 fetch + 활동 타임스탬프 갱신.
- **BR-13 (fetch 실패 = offline)**: 네트워크/HTTP 실패 → `toDashboard(null,{offline:true})`(=EMPTY offline) 모델,
  DashboardView 오프라인 표시. 직전 모델을 신선한 것처럼 유지하지 않음.
- **BR-14 (staleness)**: `isStale(model, Date.now(), STALE_THRESHOLD_MS=30000)` → DashboardView `stale` prop.
  offline·asOf 없음·파싱불가·임계초과 → stale=true.
- **BR-15 (인증)**: fetch는 기존 `serverFetcher`(basic-auth) 경로 사용. read이므로 패스키 서명 미부착(D2).
