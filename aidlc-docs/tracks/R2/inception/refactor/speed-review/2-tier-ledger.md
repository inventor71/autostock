# Tier Ledger — speed-review (R2)

범위: `src/backtest/{engine,optimizer}.py`, `src/risk/exits.py`, `src/agent/equity_log.py`,
`src/agent/tools/market.py` (참고). 우선순위: #1 라이브 지연, #2 백테스트 처리량, #3 LLM-턴 블로킹.
작성일: 2026-06-01

> Stage 1 결론 재확인: **#3(LLM 턴이 데몬을 막음)은 이미 CommandBus/prefetch로 격리** → 깨끗한
> T1 없음(멀티세션화=T3, 범위 밖). 따라서 ledger는 #1·#2 후보만 담는다.

## T1 — 동작 보존 (자율 진행)

| # | 변경 항목 | 보존되는 동작 | 보존 검증 방식 | 근거 |
|---|-----------|---------------|----------------|------|
| **C-2** | 옵티마이저 `for combo` 순차 → ProcessPool 병렬화 (`optimizer.py:59`) | `all_results` 집합·`best_params`·`best_result` 동일. **best 선택의 first-max-wins 순서 보존**(병렬 수집 후 원래 combo 순서로 재정렬해 tie-break 결정성 유지) | **신규 골든**: 고정 grid+bars로 `(best_params, all_results)` 캡처 → 병렬 전후 동일 assert | 각 combo 독립·부수효과 없음(엔진 인스턴스 분리). 임베러싱리 패러렐 |
| **C-3p** | 데몬 가격 fan-out **병렬화**(값 보존형) — `risk/exits.py:57` whole-portfolio 루프 + `equity_log.fetch_benchmark`의 per-symbol `get_latest_price`를 ThreadPool로 동시 호출 (호출/반환값은 **그대로**, 순서만 동시화) | 각 심볼이 받는 가격 = 현행과 **동일 값**(같은 `get_latest_price` 호출). 단일 심볼 실패가 나머지를 안 죽이는 best-effort 격리 동일 | `run_polled_exits` 결과 동일 + 1개 심볼 강제 실패 시 나머지 갱신·청산 동일 테스트 | 동일 호출을 동시 실행만 → 값 불변. bus 워커 점유시간↓(priority #1 직접) |
| **C-1a** | 백테스트 엔진 per-bar 슬라이스 복사 절감 — `market_data[symbol]=iloc[:i+1]`를 매 바 새 복사 대신 뷰/사전계산으로 (`engine.py:142`) | `BacktestResult`(equity_curve·round_trips·metrics) **비트 동일** | **신규 골든**: 고정 symbol+strategy+risk로 result 캡처 → 전후 동일 assert | 슬라이스 복사 제거는 값 불변(같은 데이터 동일 인덱싱) |

## T2 — 안전한 확장 (자율 진행 + 사후 보고)

| # | 추가 항목 | 기존 동작 영향 | 보존 검증 방식 |
|---|-----------|----------------|----------------|
| (없음 현재) | — | — | — |

## T3 — 의도 변경 / 기능 cut (🛑 승인 필요)

> 아래는 "cut/변경" 후보가 아니라 **동작이 바뀔 위험이 있어 T1로 자율 진행할 수 없는** 항목.
> 코드 반영 전 사용자 판단 필요. (분류 애매하면 상위 tier 원칙)

| # | 변경 내용 | 이유(복잡도/위험) | 얻는 것 | 잃는 것 | 영향 범위 | 사용자 결정 |
|---|-----------|-------------------|---------|---------|-----------|-------------|
| **C-1b** | 엔진/전략의 **per-bar 전체 지표 재계산 → incremental(rolling) 계산** (`engine.py:161` + strategy `generate_signal`) | 누적/rolling로 바꾸면 부동소수 누적오차로 **결과가 비트-동일하지 않을 수 있음**. 골든이 red면 그건 T1이 아니라 동작 변경 신호 | O(n²)→O(n) — 백테스트 처리량 최대 후보 | bit-identical 보장 깨질 위험(equity/round-trips 미세 변동) | backtest 전 전략·옵티마이저 결과 | **✅ 진행 (2026-06-01)** — 골든 red 시 허용오차 범위를 사용자와 확인 후 수용 |
| **C-3b** | 가격 fan-out을 `get_bars_multi` **단일 배치 요청**으로 (`data/base.py:45` 활용) | `get_latest_price`(latest-bar/quote 엔드포인트)와 `get_bars_multi`(historical bars)의 **반환 가격이 다를 수 있음** → 청산 판정 가격이 바뀌면 **주문 동작 변경** | HTTP N→1 (C-3p보다 큰 절감) | latest-price 의미론과 어긋나면 stop/take 트리거 값이 미세 변경 | `run_polled_exits` 주문 경로 | **❌ 미진행 (2026-06-01)** — C-3p(값 보존 병렬)만 진행 |
| **C-4** | `scoreboard` 심볼별 순차 fetch 병렬화 (`market.py:106`) | 위험 자체는 낮으나 **LLM 서브프로세스(cold CLI `python -m src.agent.tools scoreboard`) 내부**라 *다른 데몬 작업을 막지 않음*. 리서치 턴 wall-clock + reconcile 대기창만 단축 | LLM 턴 wall-clock 단축 | (없음) | 에이전트 tool 출력(값 동일) | **✅ 진행 (2026-06-01)** — 값 보존(저위험 T1), 리서치 턴 + reconcile 대기창 단축 |

> **권고**: C-1b·C-3b는 각각 C-1a·C-3p(안전한 T1 버전)로 **먼저 이득의 상당부분을 확보**하고,
> 추가 이득이 필요할 때만 승인받아 진행. C-4는 범위상 **보류** 권고.

## 특성화 테스트 매핑 (Stage 1 §D 연계)

| 후보 | 보호 테스트 | 상태 |
|------|-------------|------|
| C-2 | optimizer 결정성 골든(`all_results`+`best_params`) | **신규 작성(구현 전)** |
| C-3p | `run_polled_exits` 결과 동일 + 단일-실패 격리 | 기존 exits 테스트 확인 후 보강 |
| C-1a | engine `BacktestResult` 골든 | **신규 작성(구현 전)** |
| C-1b (T3) | C-1a와 동일 골든 — **green 유지가 cut 가능 조건** | C-1a에 의존 |

→ 보호 테스트 없는 T1 항목은 없음. C-1a/C-2 골든은 구현 착수 전 `feat/R2`에서 **먼저** 작성.

## 정지 지점
- [x] T3 항목 사용자 제시 완료 (C-1b, C-3b, C-4)
- [x] 사용자 결정 반영 + audit.md 기록 완료 (2026-06-01)

## 최종 구현 범위 (Stage 3/4 대상)
- **C-1a** 엔진 슬라이스 복사 절감 (T1)
- **C-1b** incremental 지표 (사용자 승인 — 골든 red 시 허용오차 협의)
- **C-2** 옵티마이저 ProcessPool 병렬 (T1)
- **C-3p** 데몬 가격 fetch 병렬화(값 보존) (T1) — **C-3b 배치는 제외**
- **C-4** scoreboard fetch 병렬화 (T1, 값 보존)
