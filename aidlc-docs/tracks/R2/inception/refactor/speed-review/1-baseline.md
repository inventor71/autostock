# Stage 1 — Baseline: 속도/처리량 리뷰 (speed-review, R2)

**작성일**: 2026-06-01
**범위(사용자 확정)**: 동작 보존 속도개선 후보 식별. 우선순위:
1. **라이브 데몬 지연시간** — 실거래/안전 경로의 non-LLM 작업
2. **백테스트/오프라인 처리량** — 연구 iteration 속도
3. **LLM 턴에 의해 lag되는 시스템** — 긴 LLM 턴이 *다른* 데몬 작업을 막는 경우

**범위 밖(명시)**: LLM 호출 자체의 소요시간(Claude를 빠르게 만들 수 없음). LLM 턴이 *다른 작업을
막을 때만* in-scope. `operator-console/cli/`(vendored opencode 포크) — 우리 코드 아님(R1과 동일).

---

## A. 현재 동시성/실행 모델 (정확히 고정)

리팩토링이 절대 깨면 안 되는 **현행 구조**. (priority #3의 핵심)

```
APScheduler(BackgroundScheduler, ThreadPoolExecutor=16)   # scheduler.py
   │  seconds-jobs: steer poll/snapshot/questions/monitor/order_prices/
   │                roundtrip/recent_fills + agent_wake + agent_prefetch
   │  cron-jobs:   premarket_research / open_execute / intraday / eod
   │
   ├── LLM 턴 ───► TurnCoordinator.turn_lock (단일 daily `claude --resume` 세션 직렬화)
   │                 - try_scheduled_turn: in-flight면 skip(큐잉 X)
   │                 - reconcile_turn: 우선순위 + bounded acquire(대기만 bound, LLM run은 별도 timeout)
   │
   └── executor 작업 ─► CommandBus 단일 워커 (_funnel → submit_and_wait, timeout=180s)
                          - 주문/리스크 청산/인간 명령/스냅샷이 broker·cursor를 직렬 접근
                          - EMERGENCY 우선순위 큐(긴 normal item이 yield)
```

**핵심 사실 (priority #3 결론)**: `turn_lock`은 **LLM 턴만** 직렬화한다. 주문/안전 경로
(`execute_pending`, `run_risk_exits`, 인간 명령, emergency stop)는 **별도의 CommandBus 워커**에서
돌며 `turn_lock`과 무관하다. 따라서 **긴 LLM 턴이 주문 처리/긴급정지를 막지 않는다** — 이미
F3/F14에서 분리됨(`agent_prefetch`가 BarCache를 자기 스케줄러 잡에서 예열 → 5s WakeDetector는
캐시 read만, fetch로 블록되지 않음).

**유일한 잔여 #3 항목**: 인간 *reconcile LLM 턴*은 in-flight 스케줄 LLM 턴 뒤에서 대기한다
(`turns.py` 주석: "inherent, bounded cost of the single-session model, not removed here, CQ-R1").
이를 없애려면 멀티 세션 = **동작/계약 변경(T3)** 이고, "LLM 자체는 괜찮음" 범위에서도 제외.
→ **priority #3에는 깨끗한 T1 후보가 없다. 정직한 결론: 이미 잘 격리되어 있음.**

## B. 보존해야 할 관측 가능 동작 (외부 계약 — 리팩토링 불변식)

1. **주문 경로 단일 게이트**: 인간/에이전트 트레이드 모두 `executor.execute_decision` →
   `RiskManager` 브라켓 → `Broker`. 부수효과(실주문)·사이징·보호 브라켓 동일.
2. **직렬화 보장**: LLM 턴은 `turn_lock`로, executor 작업은 CommandBus 단일 워커로 직렬.
   emergency 우선순위 동작 동일.
3. **backtest 결과 동일**: 동일 입력(symbol, bars, params, risk_config)에 대해
   `BacktestResult`(equity_curve, round_trips, metrics)가 **비트 단위로 동일**해야 함.
   특히 옵티마이저의 best 선택은 **첫 최대값 우선(first-max-wins)** 순서를 보존.
4. **가격 갱신 동작**: `run_polled_exits`의 stop/take 판정 결과, protected_symbols 스킵,
   per-symbol vs whole-portfolio 분기 동작 동일.
5. **best-effort fail 동작**: 단일 심볼 fetch 실패가 전체 체크를 건너뛰지 않는다(현행 except-pass).

## C. 속도 후보 (실측 근거 — Stage 2 ledger에서 tier 분류)

### C-1. 백테스트 엔진 inner-loop O(n²) 슬라이스/지표 재계산 — `backtest/engine.py:124-200`
```python
for i in range(warmup, len(reference_bars)):        # n bars
    for symbol in universe:
        market_data[symbol] = symbol_bars.iloc[:i+1] # [0:i] 슬라이스 복사 매 바
    ...
    signal = self.strategy.generate_signal(symbol, history, portfolio)  # 전체 history로 지표 재계산
```
- 매 바마다 모든 심볼의 `[0:i+1]` 슬라이스를 새로 복사 → O(n²) 메모리/복사.
- 전략은 매 바 **전체 history로 지표를 처음부터 재계산**(rolling 누적 아님).
- **추정 효과**: 가장 큰 오프라인 처리량 후보. n=수천 바면 제곱 비용.
- **위험도**: 지표 incremental 계산은 **수치 차이** 위험 → 반드시 특성화 테스트(정확한
  equity_curve/round_trips 골든)로 보호. 슬라이스→뷰 한정 최적화는 저위험.

### C-2. 옵티마이저 순차 실행 — `backtest/optimizer.py:59`
```python
for combo in combinations:        # 임베러싱리 패러렐
    engine = BacktestEngine(...); result = engine.run(symbol, bars)
```
- 파라미터 그리드를 **순차**로 1개씩 실행. 각 combo는 독립.
- **추정 효과**: 코어 수 배 선형 가속(ProcessPool). 동작 보존(결과 집합 동일).
- **위험도**: 낮음. 단, best 선택 first-max-wins 순서를 결정적으로 보존해야 함(결과 수집 후
  원래 combo 순서로 재정렬하여 tie-break 동일하게).

### C-3. 데몬 가격 갱신 fan-out (per-symbol 순차 네트워크) — `risk/exits.py:57`, `equity_log.py:62`
```python
for sym in portfolio.positions:               # whole-portfolio 청산 체크
    portfolio.positions[sym].update_price(data_provider.get_latest_price(sym))  # N회 순차 HTTP
...
for sym in ("SPY","QQQ","^VIX"):              # fetch_benchmark
    data_provider.get_latest_price(sym)
```
- CommandBus 워커(주문 경로와 동일 스레드)에서 N개 심볼을 **순차 HTTP**로 갱신 →
  bus 워커 점유시간↑ → 후속 주문/명령 지연(priority #1에 직접 해당).
- `data/base.py:45`에 이미 `get_bars_multi`(배치) 존재.
- **추정 효과**: N개 심볼 → 1 배치 요청. 보유 심볼 많을수록 큼.
- **위험도**: 중. 배치가 per-symbol과 **동일 가격/동일 best-effort 실패 격리**를 보장해야 함
  (한 심볼 실패가 나머지를 죽이지 않기 — 현행 except-pass 동작 보존).

### C-4. 에이전트 tool fan-out — `agent/tools/market.py:106` (`scoreboard`)
```python
for symbol in symbols:
    bars = provider.get_bars(symbol, limit=limit)   # 순차, 심볼당 + 전체 feature frame 재계산
```
- **단, 이 tool은 LLM 서브프로세스 안에서 실행** → LLM 턴 wall-clock에만 더해지고 *다른
  데몬 작업을 막지 않는다*. 사용자 스코프상 LLM 턴 길이는 "괜찮음".
- → **낮은 우선순위.** ledger에 기록하되 #1/#2보다 후순위(또는 보류) 권고.

### C-5. (참고) channel `commands.jsonl` 매 폴 top-부터 재스캔 — `steering/channel.py`
- 매 폴마다 전체 파일 재스캔 + processed-id dedup. **의도된 safety-over-speed 설계**
  (주문 경로, 저볼륨, at-least-once). 변경 = 위험(T3성). → **명시적 제외.**

## D. 특성화 테스트 현황 + 공백

| 후보 | 보호 테스트 필요 | 현황 |
|------|------------------|------|
| C-1 엔진 | equity_curve/round_trips/metrics 골든(고정 bars+strategy+risk) | **공백 — 신규 필요** |
| C-2 옵티마이저 | all_results 집합 + best_params 결정성 골든 | **공백 — 신규 필요** |
| C-3 가격 fan-out | run_polled_exits 결과 동일 + 단일 fetch 실패 격리 | 부분(exits 테스트 확인 필요) |
| C-4 scoreboard | tool 출력 dict 동일 | 기존 market 테스트 활용 가능(확인 필요) |

→ **특성화 테스트 우선 원칙**: Stage 2에서 각 T1 항목을 위 테스트에 매핑하고, 공백(C-1/C-2)은
구현 전 골든 캡처 테스트를 **먼저** 작성한다. 이 테스트는 "현재가 옳다"가 아니라 "현재가 이렇다"를
고정하는 안전망 — 리팩토링 중 red가 나면 T1이 아니라 T3 신호이므로 정지·ledger 승격.

## E. Stage 1 결론

- **#3(LLM 턴 블로킹)**: 이미 CommandBus/prefetch로 격리됨 → 깨끗한 T1 없음. (정직한 평가)
- **#1(라이브 지연)**: C-3(가격 fan-out 배치)가 유일하게 데몬 경로에 직접 닿는 실질 후보.
- **#2(백테스트)**: C-1(O(n²) 슬라이스/지표) + C-2(옵티마이저 병렬화)가 ROI 최고. 단 수치
  보존 위험이 있어 특성화 테스트가 전제.
- 모든 후보는 T1(동작 보존) 지향. 현재까지 **T3(기능 cut) 후보 없음** → T3 정지 게이트 불필요할
  전망. Stage 2 ledger에서 확정.
