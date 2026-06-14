# F82 — Functional Design

## 신규 모듈: `src/data/intraday/auto.py`
순수 오케스트레이션(주입식 provider/store/clock) — 스케줄러/데몬과 분리해 테스트 용이.

### `last_session_date(store, symbol) -> date | None`
`store.read([symbol])`의 마지막 `date`(문자열)를 `date`로 파싱. 없으면 None.

### `backfill_window(last, *, today, backfill_years) -> tuple[date, date] | None`
- `last is None` → `(today - backfill_years*365d, today)`.
- `last < today-1` → `(last + 1d, today)` (증분).
- 그 외(최신) → `None` (skip).
> 거래일 캘린더는 단순화: 주말/휴장은 provider가 빈 bars로 응답 → 세션 0개로 자연 흡수.
> 정밀 거래일 판정 불필요(과다설계). "today"는 ET 기준 주입 `clock`.

### `backfill_universe(provider, store, symbols, *, today, backfill_years, timeframe) -> dict[str,int]`
각 symbol window 계산 → 있으면 `collect(provider, [symbol], store, start, end, timeframe)`,
skip이면 0. 종목 단위 예외는 `collect()`가 격리(로그+0). 반환 `{symbol: sessions_written}`.

### `collect_today(provider, store, symbols, *, timeframe) -> dict[str,int]`
`collect(provider, symbols, store, timeframe=timeframe, limit=<2 거래일치 bars>)` 위임
(limit 경로). 그날 세션 last-write-wins upsert.

## 데몬 배선: `src/trading/modes/agent.py`
기존 패턴(`_setup_early_session`, `_run_surge_scan`) 모사.

### `_setup_intraday_collection(self)` — `start()`에서 호출
- config(`intraday_collection`) 로드. `enabled=false`면 로그 후 return(미배선).
- 인스턴스 필드 보관: `_intraday_collect_enabled`, `_intraday_store`, `_intraday_tf`.
- 백필 provider: config.provider=="alpaca"면 alpaca provider 생성(설정 키 재사용 —
  `collector._provider` 로직 공유), 아니면 `executor.data_provider`.
- `threading.Thread(target=_run_backfill, daemon=True).start()` — best-effort, startup 비차단.
  `_run_backfill` = `backfill_universe(...)`를 try/except로 감싸 로그.
- ref 보관으로 GC 방지.

### `_eod()` EOD append 추가
surge scan 근처 best-effort 블록:
```
try:
    if self._intraday_collect_enabled:
        collect_today(self.executor.data_provider, self._intraday_store,
                      list(self.executor.universe), timeframe=self._intraday_tf)
except Exception:
    logger.exception("intraday EOD collect failed (non-fatal)")
```

## 설정: `config/settings.yaml` + `config/config.py`
```yaml
intraday_collection:
  enabled: false        # 기본 OFF — 명시적으로 켜야 백필/EOD 동작
  backfill_years: 3
  provider: alpaca      # 백필 deep history; yfinance면 ~60일로 degrade
  timeframe: 5m
```
- `config.py`: settings 모델에 `intraday_collection: dict = {}`.
> **기본 OFF 근거**: 자동 백필이 의도치 않게 alpaca 다년치 호출하는 걸 막고, 운영자가
> 의식적으로 켜게 함(F60 `shorting_enabled` 보수적 디폴트 패턴).

## Testable scenarios (example-based)
1. `backfill_window`: None→full, stale→증분, 최신→None.
2. `backfill_universe`: fake provider(심볼별 bars) + 임시 store → 기대 세션수/skip.
3. `collect_today`: limit 경로 호출 + upsert 반영, 한 종목 fetch 예외 격리.
4. 게이트: enabled=false → 스레드/플래그 미생성.
5. fail-closed: provider 항상 raise → start()/_eod() 정상 완료.
