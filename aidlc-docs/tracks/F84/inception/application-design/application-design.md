# F84 Application Design — 모바일 차트 (Lightweight Charts + Solid 래퍼)

> F79 위 추가형. F79 패턴 일치: **순수 어댑터/변환(.ts, 테스트) + 얇은 뷰(.tsx, typecheck/스토리)**.
> 모든 차트 데이터는 **읽기 경로**(무서명). 외부 라이브러리는 **지연 로드**.

## 의존성 설계 (SECURITY-10)
- 추가: `lightweight-charts`(MIT, ~45KB) + `@dschz/solid-lightweight-charts@0.4.0`(피어로 위 + solid-js).
- **정확한 버전 핀**(`^` 금지) + `bun.lock` 커밋. 공식 npm 출처. postinstall/네이티브 없음 확인.
- **지연 로드**: 차트 컴포넌트를 Solid `lazy(() => import(...))`로 분리 → 번들 코드 스플릿, 차트
  마운트 시에만 라이브러리 로드(FR-6). 대시보드 초기/차트 없는 화면은 비용 0.

## 컴포넌트

### CH1. chart-data.ts (순수 어댑터 — PBT 대상)
- **책임**: 소스 데이터 → lightweight-charts 시계열 포인트로 방어적 변환.
  - `toCandles(bars): CandlestickData[]` — {time, open, high, low, close}, 시간 오름차순 정렬,
    중복 ts dedupe, 비유한값 제거, never-throw.
  - `toAreaSeries(points): (LineData|AreaData)[]` — equity {time, value} 동일 규약.
  - `toDecisionMarkers(decisions): SeriesMarker[]` — 매수/매도/관망 → 위치/색/모양(FR-3).
- 시간 표현은 lightweight-charts `Time`(UTCTimestamp 초) 규약으로 정규화.

### CH2. chart-theme.ts (순수 — 테마 옵션 생성)
- **책임**: 현재 테마(light/dark) → lightweight-charts `ChartOptions`(layout 배경/텍스트, grid,
  상승/하락 색). host 토큰의 계산값(CSS var resolved) 또는 매핑 상수로 산출. 테마 전환 시 재계산.
- 상승=success / 하락=critical 의미색을 F79와 동일하게.

### CH3. PriceChart.tsx (뷰, FR-1/FR-3/FR-5)
- **책임**: `@dschz/solid-lightweight-charts`의 `TimeChart` + `TimeChart.Series`(Candlestick 기본,
  Line 토글)로 시세 렌더. 컨테이너 명시 크기. props: `candles`, `markers?`, `theme`, `range`,
  `onRangeChange?`, `loading?`. loading/no-data fallback. lazy-wrapped로 export.

### CH4. EquityChart.tsx (뷰, FR-2)
- **책임**: equity area/sparkline(`TimeChart` Area/Line). props: `points`, `theme`, `loading?`.
  데이터 없으면 렌더 안 함(레이아웃 안정). 컴팩트 변형(대시보드 히어로 아래).

### CH5. RangeToggle.tsx (뷰, FR-5)
- 1D/1W/1M 등 세그먼트 토글 → `onRangeChange`. host 토큰 스타일.

## F79 통합 지점 (스택 — 같은 파일 수정)
- `detail-views.tsx::PositionThesisView` — thesis 위에 `PriceChart`(+RangeToggle) 삽입.
- `dashboard-view.tsx` — 히어로 카드 아래 `EquityChart` 삽입(선택적, 데이터 있을 때).
- 데이터: 셸이 SDK read로 OHLC/portfolio history 조회 → CH1 변환 → 뷰. 마커는 F79 agent.recent → CH1.

## 데이터 흐름
```
SDK read (stock bars / portfolio history, 무서명)
  → chart-data(CH1) 방어적 변환(정렬·dedupe·유한)
  → PriceChart/EquityChart(lazy)  ← chart-theme(CH2) ← theme context(light/dark)
  range 토글 → onRangeChange → 셸이 재요청 → 갱신
  agent.recent(F79) → toDecisionMarkers → series markers
실패/누락 → no-data/loading fallback (never-throw, fail-safe)
```

## 보안 (Security Baseline) 매핑
- SECURITY-10: 버전 핀 + lockfile + 공식 출처 + postinstall 없음 + 번들 예산.
- SECURITY-15: CH1/CH2 never-throw, no-data degrade; 외부 응답 방어적 파싱.
- N/A: 데이터스토어/네트워크/IAM/auth 인프라 없음. 차트=읽기(무서명) → WebAuthn 무관.

## 테스트 설계 (PBT — PBT-01 식별)
- **라운드트립/불변식(PBT-02/03)**: 임의 bars/points/decisions →
  - 출력 시간 **오름차순 정렬** 보장, **중복 ts 없음**, 모든 값 **유한**, 입력 ⊇ 출력(필터만),
    `toCandles`/`toAreaSeries`/`toDecisionMarkers` **never-throw**.
- **예시(PBT-10)**: 빈 입력 → 빈 배열; 뒤섞인 ts → 정렬; NaN/Infinity 섞임 → 제거.
- **프레임워크(PBT-09)**: fast-check(기존). 시드 로깅/shrink 유지.
- **뷰**: typecheck(tsgo) + Storybook 스토리(PriceChart 캔들/라인/마커/no-data/loading, EquityChart
  area/no-data, 라이트·다크) + playwright 스냅샷.

## 단위(Units)
- 단일 유닛(작음): CH1/CH2(+테스트) → CH3/CH4/CH5(뷰+스토리) → F79 통합 삽입 → 데이터 배선
  (F79 셸 통합과 함께). Units Generation 스킵.

## 검증
- 트랙 내: chart-data/chart-theme PBT+예시, tsgo 클린, Storybook 라이트/다크 스냅샷.
- post-merge: 실데이터(브로커 bars/portfolio history)로 차트 1회 확인(F79 통합 후).

## 미해결/결정 필요 (Construction 진입 전 확인 권장)
1. **데이터 소스 확정**: 포지션 OHLC = 어느 read tool(Alpaca `get_stock_bars`?), 해상도(분/일);
   equity = portfolio history tool. F79 통합 시 실엔드포인트 매핑.
2. **기본 차트 타입**: 캔들 기본 vs 라인 기본(모바일 가독성). (권장: 라인 기본 + 캔들 토글)
3. **F79 머지 전략**: 스택 개발 후 F79와 순차 머지 vs F79 머지 대기 후 rebase.
