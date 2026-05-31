# F14 Functional Design (U1 + U2)

> Application Design 흡수. UI 없음(데몬/런처) → frontend 산출물 생략. 동작 정의 위주.

## FD-A. broker/데이터 HTTP 타임아웃 (U1.A)
- **동작**: `AlpacaBroker`·`AlpacaDataProvider`가 거는 모든 Alpaca HTTP 호출은 connect 3s/read 5s를
  초과하면 `requests.exceptions.Timeout`을 raise한다. 이 예외는 기존 호출부의 best-effort
  `try/except`(BarCache.get_*, publish_snapshot `_build`, broker 메서드 내부)가 잡아 다음 tick 재시도.
- **불변식**: 단일 HTTP 호출이 (connect 3s + read 5s) 이상 블록되지 않는다 → 어떤 워커/스케줄러
  스레드도 한 호출로 영구 정지 불가 (AC-A).
- **⚠️ critic [HIGH] 반영 — 3개 클라이언트 전부 래핑 (특히 lazy `_data_client`)**:
  AlpacaBroker는 클라이언트가 **둘**이다 — ctor의 `self._client`(TradingClient) **그리고**
  `get_latest_prices` 안에서 **첫 호출 시 lazy 생성**되는 `self._data_client`
  (`alpaca_broker.py:362-364`). 이 lazy 클라이언트는 `steering_order_prices`(12s job) 경로가 쓰며
  ctor 시점엔 존재하지 않으므로 **ctor 훅으로는 절대 안 닿는다.** → 타임아웃 헬퍼를
  `get_latest_prices`의 lazy 생성 직후(`alpaca_broker.py:364` 다음 줄)에도 적용해야 한다.
  안 그러면 그 경로의 half-open 블록으로 wedge가 그대로 재발(A가 B의 원인을 비껴감). 적용 대상 총 3:
  TradingClient(`broker._client`) · 데이터 provider(`AlpacaDataProvider._client`) · broker lazy `_data_client`.
- **⚠️ 페이지네이션 주의 (LOW)**: read 5s는 **요청당** 적용이라 페이지네이션 호출(get_fills 등)은
  전체가 5s×N 가능. detect_wakes 경로는 단일 GET(limit=50)이라 무관. AC-A는 "단일 호출"로 한정.

## FD-B. WakeDetector 동기 fetch 분리 (U1.B)
- **현 동작(결함)**: `detect_wakes`(스케줄러 5s job) → `_abnormal_events`/`_watch_events` →
  `BarCache.get_price/get_bars`가 **캐시 미스 시 동기 HTTP**. price_ttl(3s)<루프(5s)라 매 tick fetch.
- **새 동작**:
  1. `BarCache`에 **캐시 전용 read** `peek_price(sym)`/`peek_bars(sym)` 추가 — 캐시에 있으면 값,
     없으면 `None`(절대 fetch 안 함, TTL 무관).
  2. `detect_wakes`는 `peek_*`만 사용 → 스케줄러 스레드에서 네트워크 0 (docstring 불변식 실제 충족).
  3. 신규 **prefetch 워커**가 held+watched 심볼에 대해 주기적으로 `get_price`(5s)/`get_bars`(60s,
     bars_ttl 게이트)를 호출해 캐시를 채운다. 심볼 소스 = `held_and_watched(snapshot, watch_store)`
     (기존 `_intraday_symbols`와 동일).
- **결과**: detect_wakes tick은 캐시 dict 읽기뿐 → ms 단위 종료 → `max_instances` skip 소멸 (AC-B).
  prefetch 워커가 타임아웃(FD-A)으로 stall돼도 detect_wakes는 영향 없음(분리됨).
- **데이터 신선도**: peek는 직전 prefetch 결과를 보므로 최대 1 prefetch 주기(가격 5s)만큼 지연 —
  이전(매 tick 실시간 fetch) 대비 wake 판정에 실질 차이 없음(가격 트리거/abnormal은 5s 해상도로 충분).
- **None 처리 (⚠️ critic R1[MEDIUM]+R2[HIGH] 반영 — 정정)**: 현재 `_abnormal_events`는 `detect_abnormal`이
  None이면 무조건 `_abnormal_fired.discard(sym)`로 re-arm한다(`wake.py:126-127`). 그런데
  `detect_abnormal`은 price/bars None일 때도 None을 반환한다 — price 분기는 price+bars 둘 다,
  volume 분기는 bars 필요(`abnormal.py:45,53`). 즉 "데이터 없음(peek miss)"과 "신호 없음(정상값
  임계 미달)"이 둘 다 None으로 합쳐져 구분 불가이고, peek 전환 시 캐시 미스가 늘어 **re-arm 오작동
  (같은 episode 중복 wake)**이 악화된다.
  - ⚠️ **R3 정정 (R2의 `or`도 틀림)**: critic R3 — price만 None(bars 정상)은 가격 5s·바 60s 독립
    TTL 때문에 흔한데, `detect_abnormal`은 **price 없이도 volume 분기로 신호를 낼 수 있다**
    (abnormal.py:52-55, ATR 분기만 price+ref 필요). `or` 가드로 price None을 무조건 continue하면
    **volume-abnormal wake를 놓친다**. (`and`는 latch re-arm, `or`는 volume 누락 — 둘 다 결함.)
  - → **확정 수정 (2단계)**: `_abnormal_events`에서 **detect를 먼저 호출**하고:
    ```
    sig = detect_abnormal(sym, price, ref, bars, cfg)
    if sig:        # 신호 → 기존대로 latch/ fire
        ...
    elif price is not None and bars is not None and len(bars) > 0:
        self._abnormal_fired.discard(sym)   # 데이터 충분 + 무신호 = 진짜 episode clear → re-arm
    else:
        continue                            # 데이터 부족(peek miss) = 판정 보류, latch 유지
    ```
    → volume-only abnormal도 안 놓치고, 캐시 미스로 인한 잘못된 re-arm도 없음.
- **watch peek-miss (LOW, ⚠️ R2 근거 정정)**: `_watch_met`는 peek None이면 False(미충족)로 두되
  `mark_fired`는 fire 시점에만 하므로 트리거를 **소비하지 않는다**(다음 tick 재평가). 단 근거 정정:
  기존 `get_price`는 캐시 미스 시 **즉시 동기 fetch라 항상 값**을 얻었고(`bars.py:71-82`), peek는 캐시
  없으면 무조건 None이라 "5s 샘플링이라 동일"은 틀림. 안전성의 진짜 근거는 **prefetch 심볼 소스가
  `held_and_watched`(util.py:6-17)라 watch 심볼을 포함** → prefetch가 그 심볼을 채운다는 것.
  따라서 갭은 "watch 추가 후 첫 prefetch 1주기"로 한정.
- **BriefAssembler**: 변경 없음 — 턴 스레드(스케줄러 아님)에서 실행되므로 `get_*` fetch 허용,
  이제 FD-A 타임아웃으로 bounded.

## FD-C. 런처 self-heal (U2.C) — ⚠️ critic R1+R3 반영, **최종 (advance-only 폐기)**
**정정 1 (R1)**: active+wedge는 **이미 감지된다**. not-fresh이면 `ensureRunning`이 `healthWait()`로
떨어지고(daemon.ts:267), 그 메시지가 사용자가 본 `snapshot not advancing within Ns`이다(daemon.ts:308).
실제 작업은 "새 감지 분기"가 아니라 **(a) active+not-fresh 경로의 patience를 60s→3분, (b) wedge 확정 시
자동 restart 1회**.

**정정 2 (R3 — advance-only 폐기, `fresh && advanced` 유지)**: 기존 `healthWait`(daemon.ts:296-310)는
healthy 판정의 실제 트리거가 **다음 advance**(`pub > initial`, daemon.ts:302; `initial`은 진입 시 1회
스냅)이고 거기에 `fresh`(45s)를 AND한다. 느린-정상 데몬도 **다음 publish에서 advance가 잡혀** healthy가
된다 — 최악 대기 = **1 publish 주기**(fresh 게이트가 막는 게 아님). fresh를 빼면 "죽어가며 마지막
publish 1회"가 폴링 중 도착하는 레이스로 죽은 데몬을 attach할 위험만 생긴다(daemon.ts:291-294가 둘 다
요구하는 이유). → **`fresh && advanced` 유지, 기존 `healthWait` 그대로 재사용, timeout만 조절. 새 헬퍼
불필요.** (안전 조건: `WEDGE_PATIENCE_MS ≥ 최악 publish 주기 + HEALTH_WINDOW_MS`. 180s는 최악 주기
≤135s 가정 — 현 규모 충족.)

- **새 흐름** (기존 `ensureRunning` daemon.ts:240-275에 active 분기 삽입):
  1. `isFreshNow()` → fresh면 attach (변경 없음).
  2. not-fresh → `ensureInstalled` → `state()`:
     - `failed` → 기존 진단 throw.
     - **`active`** (wedge 후보) → 별도 헬퍼로 빼서 **early-return**(critic R3 [HIGH]: 그냥 끼우면
       restart 후 공통 :267 `healthWait`가 한 번 더 돌아 **이중 healthWait**가 됨):
       1. `healthWait(WEDGE_PATIENCE_MS=180s)` (fresh&&advanced) → healthy면 `return`(busy/slow였음).
       2. unhealthy → **restart 직전 `isFreshNow()` 레이스 가드**(active 경로엔 신규 추가 — daemon.ts:258은
          inactive 경로에만 있음) → 여전히 wedge면 `systemctl --user restart` **1회**.
       3. `healthWait(RESTART_HEALTH_MS=180s)` → healthy `return` / unhealthy **fail-closed throw**.
     - `active` 아님 → 기존 start → :267 `healthWait(60s)` (완전히 변경 없음).
- **restart 후 대기 180s (R3 정정)**: round-2의 "60s 충분" 근거("fresh window를 폴링이 잡는다")는 틀렸다
  — healthy는 다음 advance에서 나며, restart 직후 디스크의 낡은 snapshot이 `initial`로 찍히고 새 데몬의
  첫 publish가 그보다 커질 때 advance=true가 된다. 보통 ~5–10s지만(아래 참조) 안전 마진으로 60s 대신
  `RESTART_HEALTH_MS=180s` 사용(false-negative 제거; 다운사이드는 실패 보고 지연뿐).
- **published_at vs 턴/배치 (정밀)**: published_at은 `publish_snapshot._build`가 **CommandBus(bus)에
  submit**(runtime.py:180)되어 스탬프된다(channel.py:180). 한편 **LLM 턴은 turn_lock**(`_scheduled_turn`
  →`coordinator`, agent.py:135-144)에서 돌고 **bus를 쓰지 않는다** → **긴 리서치/인트라데이 LLM 턴은
  published_at을 얼리지 않는다**(FR-C4 핵심 안전성 성립, 콜드스타트 publish도 ~5–10s). publish를 지연시킬
  수 있는 유일한 것은 **executor 배치**(`_funnel`→bus, agent.py:127-133)뿐이고, 이는 FR-A 타임아웃 +
  보유 ~5–10종목으로 bounded(≪3분). → critic의 "turn이 bus 점유" 프레이밍은 부정확(턴=turn_lock).
  **잔여 리스크** = 대형 executor 배치가 bus 점유 시 일시 publish 지연(현 규모 안전; 유니버스 확장 시
  patience 상향 재검토).
- **상태**: 1회성(인터랙티브 실행당 restart 1회). 백그라운드 watchdog/백오프는 스코프 밖.
