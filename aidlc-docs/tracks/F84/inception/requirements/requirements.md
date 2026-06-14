# F84 Requirements — 모바일 PWA 차트 (Lightweight Charts), F79 위 추가형

> Track F84 · 단일 작성자 = F84 worktree 세션. **F79 의존(스택)**. OSS 조사 결론(풀 스톡 앱은
> 임베드 부적합, 차트 라이브러리만 채택)에 따른 *추가형* 트랙 — 기존 모바일 뷰를 대체하지 않음.

## Intent Analysis
- **User Request (원문)**: "차트를 얹는걸 해당 repo를 참고해서 할 수 있도록 상세한 ai-dlc 트랙을 만들어줘"
- **Request Type**: New Feature (추가형 — 기존 F79 모바일 뷰에 차트 표면 추가).
- **Scope Estimate**: Single Component (`operator-console/cli/packages/app` 내부 + 신규 의존성 2).
- **Complexity Estimate**: Moderate — 외부 라이브러리 채택 + 테마 연동 + 데이터 변환 + 지연로드.
- **Depth**: Standard.

## 채택 기술 (조사 확정)
- **TradingView Lightweight Charts** — MIT, ~45KB, Canvas 기반 금융 차트. `createChart` → `IChartApi`.
- **`@dschz/solid-lightweight-charts`** v0.4.0 — SolidJS 선언형 래퍼(npm/GitHub `dsnchz/solid-lightweight-charts`).
  - 설치: `bun add @dschz/solid-lightweight-charts` + 피어 `solid-js`(기존) `lightweight-charts`.
  - 컴포넌트: `TimeChart`(+ `TimeChart.Series` type=`Candlestick`/`Line`/`Area`), `PriceChart`, 마커(`onSetMarkers`/setMarkers).
  - 컨테이너에 **명시적 크기** 필요(CSS/인라인).
- 참고 레퍼런스(디자인만, 코드 import 아님): OpenStock/Signalist(레이아웃), TradingView 공식 docs.

## 배경 (현 상태 — F79)
F79가 모바일 뷰를 완성: `dashboard-view.tsx`(리치 모델 + `PositionRow` + 에이전트 활동),
`detail-views.tsx`(`PositionThesisView`/`HealthOverlay`). 현재 **차트는 없음** — 숫자/행만. 본 트랙이
시세/자산 차트를 그 위에 얹는다.

## Functional Requirements

### FR-1 — 포지션 상세 시세 차트
- `PositionThesisView`(또는 포지션 상세)에 해당 종목의 **시세 차트**(캔들 기본, 라인 토글 가능)를 표시.
- 데이터: OHLC bars(일중 또는 N일) — SDK read(브로커 stock bars) 경유, 읽기전용(무서명).
- loading / no-data / 조회 실패는 각각 명시적 표시(차트 자리에 fallback, fail-safe).

### FR-2 — 홈 자산 곡선
- 대시보드 히어로(총 자산) 아래 **equity area/sparkline**(일중 또는 누적 portfolio history).
- 데이터: portfolio history(시간별 equity) — SDK read 경유. no-data면 차트 숨김(레이아웃 안정).

### FR-3 — 에이전트 결정 마커 (추가 가치)
- 시세 차트 위에 **에이전트 결정 시점 마커**(매수/매도/관망)를 오버레이(F79 agent activity와 연계,
  lightweight-charts series markers). 데이터 없으면 마커 없이 차트만. (선택적 — 데이터 가용 시)

### FR-4 — 시스템 테마 연동
- 차트 배경/그리드/색을 **host light/dark 토큰**과 매칭하고, 테마 전환 시 **반응형 갱신**.
  상승/하락 색은 F79와 동일 의미색(success/critical) 사용.

### FR-5 — 시간 범위 토글
- 간단한 레인지 토글(예: 1D / 1W / 1M). 선택에 따라 데이터 재요청 + 차트 갱신.

### FR-6 — 지연 로드(성능)
- 차트 라이브러리는 **lazy import(코드 스플릿)** — 차트가 실제로 마운트될 때만 로드. 차트 없는
  화면(대시보드 최초 등)엔 번들/런타임 비용 0에 가깝게.

## Non-Functional Requirements

### NFR-1 — 보안 (Security Baseline)
- **SECURITY-10 (공급망)**: 신규 의존성 `lightweight-charts` + 래퍼를 **정확한 버전 핀** + lockfile
  커밋 + 공식 npm 출처. postinstall/네이티브 빌드 없음 확인. 번들 사이즈 예산 점검(~45KB+래퍼).
- **SECURITY-15 (fail-safe)**: 차트 입력(서버/SDK 응답)은 방어적 파싱 — 잘못된/누락 데이터에
  never-throw, no-data로 degrade. 시세는 **읽기 경로**(무서명; mutating 아님 → WebAuthn 무관).
- N/A: 차트는 데이터 저장/네트워크 인프라 없음(SECURITY-01/02/06/07).

### NFR-2 — 성능
- lazy-load + 데이터 포인트 수 캡(예: 일중 N분봉/누적 포인트 상한). 모바일에서 부드러운 초기 렌더.

### NFR-3 — 호환/접근성
- 모바일 브라우저 Canvas. 라이트/다크. 핀치줌/팬은 lightweight-charts 기본(옵션으로 조정).
  색만으로 상승·하락 구분하지 않도록 ▲▼/라벨 병행(F79 일관).

### NFR-4 — 테스트 (PBT)
- **PBT-09**: fast-check(F79와 동일, 이미 의존성). **PBT-02/03**: 소스 bar/equity → 차트 시계열
  변환 순수함수의 라운드트립/정렬(시간 오름차순)/유한값/dedupe 불변식 + never-throw.
- 컴포넌트는 typecheck + **Storybook 시각 검증**(라이트/다크/no-data/loading), playwright 스냅샷.

### NFR-5 — 유지보수성
- 차트 **어댑터(순수 변환) + 얇은 뷰** 분리(F79 패턴 일치). 래퍼/라이브러리 버전 핀. 차트 옵션
  생성(테마)도 순수 함수로 테스트 가능하게.

### NFR-6 — 데이터 출처 (통합 의존)
- 포지션 OHLC + portfolio history의 실제 소스(Alpaca/KIS read tools, steer_read)를 매핑. **데이터
  배선은 F79 셸 통합(C8/C10)과 함께** — 본 트랙은 차트 컴포넌트 + 변환 + 테마 + 스토리 + (가능 시)
  실데이터 연결.

## Scope / Out-of-Scope
**In**: lightweight-charts(+solid 래퍼) 채택, 포지션 시세 차트(FR-1), 자산 곡선(FR-2), 결정 마커
(FR-3), 테마 연동(FR-4), 레인지 토글(FR-5), 지연로드(FR-6), 변환 PBT + 스토리.
**Out**: 기술지표/드로잉 툴, 실시간 틱 스트리밍(후속), 차트상 주문(범위 밖), 워치리스트/공개시세
탐색, **풀 OSS 스톡 앱 채택(조사 결과 부적합)**.

## 핵심 요약
F79 모바일 뷰에 **검증된 MIT 차트 라이브러리(lightweight-charts) + SolidJS 래퍼**를 *추가형*으로
얹어 포지션 시세·자산 곡선·결정 마커를 시스템 테마로 보여준다. 트랙은 **F79에 스택**하며 단독
머지 불가. 데이터 무결성 fail-safe·의존성 핀·지연로드가 비기능 핵심.
