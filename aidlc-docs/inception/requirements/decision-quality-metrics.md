# Decision Quality Metrics — 요구사항

## 1. 의도 분석

- **요청 명확도**: Clear — 이전 대화에서 메트릭 목록, 데이터 소스, 기존 코드 대비 격차가 상세히 논의됨
- **요청 유형**: New Feature — 기존 `outcome_lines()` 텍스트 스냅샷을 보완하는 정량 분석 레이어
- **범위**: Single Component — 새 `src/agent/quality/` 모듈 + CLI 진입점 + EOD 프롬프트 연동
- **복잡도**: Moderate — 순수 데이터 분석이지만 메트릭 종류가 다양하고 데이터 소스 3개 통합
- **요구사항 깊이**: Standard

## 2. 기능 요구사항

### FR-1: 데이터 수집 레이어
decisions.jsonl + Alpaca fills/activities API + yfinance 가격 히스토리를 통합하여
분석 가능한 `DecisionOutcome` 레코드 리스트를 생성한다.

- **FR-1.1**: `decisions.jsonl`에서 `Decision` 객체를 파싱한다 (기존 `Journal.read_decisions()` 재사용).
- **FR-1.2**: Alpaca fills/activities API에서 실제 체결 데이터를 조회한다 (기존 `get_fills()` 재사용).
  `get_fills()`는 `list[FillEvent]` (Pydantic)을 반환하므로 `match_round_trips()`가 기대하는
  `list[dict]` 형식으로 **변환 레이어**가 필요하다 (기존 패턴: `steering/runtime.py:260-264`).
  또한 `trades_log.py`의 orders 기반 `_alpaca_fills()`와 activities 기반 `get_fills()`는
  다른 API — partial fill 정밀도를 위해 **activities 기반 `get_fills()`를 사용**한다.
- **FR-1.3**: `match_round_trips()` (src/core/trades.py)로 FIFO 라운드트립을 매칭한다.
- **FR-1.4**: yfinance에서 일봉(daily OHLC) 가격 경로를 조회한다. **심볼별 배치 fetch**
  (round-trip별 개별 호출 X): 유니크 심볼 목록 추출 → 심볼당 1회 yfinance 호출
  (earliest opened_at ~ latest closed_at+N일) → 메모리 캐시. NFR-1(10초) 준수를 위해 필수.
- **FR-1.5**: Decision→Fill 조인에는 **영속적 링크 키가 필요**하다.
  현재 `Decision`에 `order_id` 없고, `ExecutionOutcome`(executor.py:33-37)은 휘발성.
  **해결책**: `DecisionExecutor`가 실행 후 `execution_log.jsonl`에
  `{decision_index, symbol, action, order_id, filled_qty, filled_price, ts}`를 append.
  품질 모듈은 이 로그로 Decision↔Fill을 정확히 매칭한다.
  execution_log가 없는 과거 결정은 심볼+시간 휴리스틱으로 best-effort 매칭 (경고 표시).
- **FR-1.6**: MAE/MFE를 위해 round-trip 레코드에 **보유 기간 일봉 가격 경로를 조인**한다.
  `match_round_trips()` 출력의 `[opened_at, closed_at]` 구간에 해당하는 daily OHLC를
  FR-1.4의 배치 캐시에서 슬라이싱하여 `DecisionOutcome.price_path: list[OHLC]`로 첨부.

### FR-2: 핵심 메트릭 계산
각 `DecisionOutcome`에서 다음 메트릭을 계산한다:

- **FR-2.1 방향 적중률**: **BUY만 측정** — BUY 후 N일(기본 5일) 수익률 양수 비율.
  SELL은 이 시스템에서 "포지션 청산"(long-only)이므로 방향 적중과 무관 — SELL은 FR-2.7
  실현 R:R과 FR-2.9 exit timing quality로 평가한다. HOLD/ADJUST_STOP은 제외.
- **FR-2.2 MAE (Maximum Adverse Excursion)**: 진입가 대비 보유 기간 중 최대 역행폭
  (일봉 low 기준). `price_path`의 min(low) 사용.
- **FR-2.3 MFE (Maximum Favorable Excursion)**: 진입가 대비 보유 기간 중 최대 순행폭
  (일봉 high 기준). `price_path`의 max(high) 사용.
- **FR-2.4 Stop 품질**: stop이 트리거된 경우 — 트리거 후 N일간 가격이 stop 아래 유지됐으면
  "적절", 반등했으면 "noise hit" (premature stop). 트리거 안 된 경우 — 가격이 stop 근처까지
  왔다가 반등했으면 "잘 버팀".
- **FR-2.5 Target 품질**: target 도달 여부 + 도달까지 걸린 일수 (자본 효율성).
- **FR-2.6 Confidence 캘리브레이션**: confidence 구간별 실제 적중률.
  **`confidence=0.5` (기본값) 또는 `None`은 "unscored"로 분류하여 캘리브레이션에서 제외.**
  journal.py:47에서 기본값 0.5가 LLM 미지정 시 할당되므로, 이를 포함하면 캘리브레이션 무의미.
  유효 구간: (0.0–0.49), (0.51–0.7), (0.7–0.9), (0.9–1.0).
- **FR-2.7 실현 R:R**: 계획 risk:reward (|entry–stop| vs |entry–target|) 대비 실현 R:R
  (실제 손익 / 실제 리스크 노출). 계획 R:R이 없는 결정(stop/target 미지정)은 제외.
- **FR-2.8 벤치마크 대비 초과 성과**: 동일 보유 기간 SPY/QQQ 수익률 대비 초과 수익.
- **FR-2.9 Exit Timing Quality** (SELL 전용): SELL 후 N일간 가격 변동으로 청산 타이밍 평가.
  "기회비용" = SELL 후 추가 상승폭 (양수=too early, 음수=good timing).

### FR-3: 집계 + 롤링 윈도우
- **FR-3.1 전체 기간 집계**: 전체 decisions.jsonl에 대한 각 메트릭의 평균/중앙값/분포.
- **FR-3.2 롤링 윈도우**: 최근 N건(기본 20건) 단위로 메트릭 롤링 계산 → 시간에 따른
  개선/악화 트렌드 파악.

### FR-4: CLI 리포트
- **FR-4.1**: `python -m src.agent.quality` (또는 `python -m src.agent.quality report`)
  실행 시 Rich 테이블로 터미널에 출력.
- **FR-4.2**: JSON 형식으로 `workspace/quality/<date>.json`에 저장.
- **FR-4.3**: 요약 섹션 (전체 통계) + 상세 섹션 (결정별 메트릭) + 롤링 트렌드 섹션.

### FR-5: EOD 리뷰 프롬프트 연동
- **FR-5.1**: EOD 리뷰 턴에 최근 메트릭 스냅샷(방향 적중률, 평균 MAE/MFE, stop 품질 비율,
  confidence 캘리브레이션 요약)을 프롬프트에 주입한다.
- **FR-5.2**: `src/agent/prompts.py`의 `eod_review_prompt()`에 선택적 `quality_summary: str | None`
  파라미터를 추가한다. **호출 체인 3파일 수정 필요:**
  - `prompts.py` — 파라미터 추가 + 프롬프트 템플릿
  - `orchestrator.py:136` (`run_eod_review`) — quality_summary 전달
  - `modes/agent.py:203` (`_eod`) — quality 모듈에서 스냅샷 계산 후 전달
- **FR-5.3**: 데이터가 부족하면(결정 < 5건) 주입하지 않는다 (fail-safe).
  `quality_summary=None`일 때 프롬프트에 "None" 문자열이 들어가지 않도록 가드.

## 3. 비기능 요구사항

- **NFR-1 성능**: CLI 리포트는 100건 결정 + 1년 일봉 데이터 기준 10초 이내.
  yfinance 호출은 심볼별 배치 (20심볼 × 1회 ≈ 10-20초 → 캐시 필수).
- **NFR-2 의존성**: 0 신규 런타임 의존성 (pandas/numpy/yfinance/alpaca-py/rich 재사용).
- **NFR-3 테스트**: Hypothesis PBT를 순수 메트릭 함수에 적용 (PBT-02/03, Partial mode).
- **NFR-4 보안**: SECURITY-03 (로그에 비밀 미포함), SECURITY-15 (fail-closed — 데이터 부족 시
  빈 리포트, 에러 아님).
- **NFR-5 아키텍처**: 기존 라이브/백테스트 경로에 영향 없음. 읽기 전용 분석 모듈.
  단, `DecisionExecutor`에 `execution_log.jsonl` append 추가 (FR-1.5) — 실행 경로 최소 변경.

## 4. 범위 제외

- **통계 검증** (Monte Carlo, Bootstrap, Walk-Forward) — v1 제외 (미래 고려 가능).
- **Paper Tournament** (Layer 2) — 별도 트랙.
- **인트라데이(5분봉) MAE/MFE** — v1은 일봉만.
- **자동 프롬프트 수정** — 메트릭 기반으로 프롬프트를 자동 변경하는 것은 범위 밖.

## 5. 데이터 흐름

```
decisions.jsonl ───┐
                   │     execution_log.jsonl
Alpaca fills API ──┤──→  (decision→order_id 링크)
                   │           │
                   │     FillEvent→dict 변환
                   │           │
                   │     match_round_trips()
                   │           │
                   ├──→  DecisionOutcome 조인 ──→ 메트릭 계산 ──→ CLI 리포트
                   │           │                                  + JSON 저장
yfinance daily ────┘     price_path 조인                          + EOD 주입
(심볼별 배치 fetch)    (보유 기간 OHLC 슬라이싱)
```

## 6. 기존 코드 재사용

| 기존 모듈 | 재사용 방식 |
|---|---|
| `src/agent/journal.py` | `Journal.read_decisions()` — 결정 파싱 |
| `src/agent/review.py` | `outcome_lines()` 패턴 참고 (데이터는 별도 수집) |
| `src/core/trades.py` | `match_round_trips()` — 라운드트립 매칭 (입력: `list[dict]`) |
| `src/data/base.py` | yfinance 데이터 조회 (`get_bars` with start/end) |
| `src/execution/brokers/alpaca_broker.py` | `get_fills()` → `list[FillEvent]` (변환 필요) |
| `src/agent/steering/runtime.py:260-264` | FillEvent→dict 변환 패턴 참고 |
| `src/backtest/metrics.py` | 참고만 — 키 불일치(`pnl` vs `realized_pnl`), 자체 함수 작성 |

## 7. Critic 검토 반영 (2026-06-01)

8 findings (HIGH 3, MED 3, LOW 2), 전부 엔지니어링 보강으로 반영:
- **#1 [HIGH]**: FR-1.5에 `execution_log.jsonl` 영속화 추가
- **#2 [HIGH]**: FR-1.6에 price_path 조인 단계 + 심볼별 배치 fetch 명시
- **#3 [HIGH]**: FR-1.2에 FillEvent→dict 변환 레이어 명시
- **#4 [MED]**: FR-5.2에 호출 체인 3파일(prompts/orchestrator/agent) 명시
- **#5 [MED]**: FR-2.1을 BUY만으로 재정의, SELL은 FR-2.9 exit timing으로 분리
- **#6 [MED]**: FR-2.6에 confidence=0.5/None "unscored" 필터 추가
- **#7 [LOW]**: 재사용 표 수정 (backtest/metrics.py → 참고만)
- **#8 [LOW]**: state.md 범위 정렬 (별도 수정)
