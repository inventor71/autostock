# surge-detection — Business Logic Model

> Functional Design | 2026-06-03

## Component Structure

```
src/surge/
├── __init__.py
├── records.py      # SurgeRecord, SurgeAnalysis, SurgeCause data models (pydantic)
├── detector.py     # SurgeDetector — price fetch + return calc + threshold filter
├── store.py        # SurgeStore — JSONL read/write with idempotency
└── settings.py     # SurgeDetectionConfig — settings.yaml surge: block parser

src/agent/tools/market.py  # + surge_list(), surge_analyze() — agent-facing tools
config/settings.yaml       # + surge: block
```

---

## BL-1: SurgeDetector — 급등/급락 감지

### BL-1.1: scan() 메인 플로우

```python
def scan(
    universe: list[str],
    data_provider: DataProvider,
    config: SurgeDetectionConfig,
    today: date | None = None,
) -> list[SurgeRecord]:
```

1. `today`가 None이면 `date.today()` 사용
2. `data_provider.get_daily_bar(symbol, today)` 로 각 종목의 당일 OHLCV + 전일 종가 조회
3. 각 종목에 대해:
   a. `change_pct = (close_today - close_prev) / close_prev * 100`
   b. `abs(change_pct) >= config.threshold_pct` → 급등/급락 후보
   c. `change_pct > 0` → `direction = "up"`, else `"down"`
   d. 20일 평균 거래량 조회 → `volume_ratio` 계산
   e. `SurgeRecord` 생성
4. 실패한 종목은 로그만 남기고 skip (fail-isolated)
5. 결과를 `abs(change_pct)` 내림차순 정렬

### BL-1.2: 데이터 조회

- 가격 데이터: `DataProvider.get_daily_bar(symbol, date)` → OHLCV dict
  - yfinance: `yf.Ticker(symbol).history(start=date, end=date+1day)`
  - Alpaca: `GetBarsRequest(symbol, timeframe=Day, start=date, end=date+1day)`
- 전일 종가: `date - 1 trading day` 의 close (주말/휴일 처리)
- 20일 평균 거래량: `date - 20 trading days` ~ `date - 1 trading day` 구간 volume 평균

### BL-1.3: Fail-Isolated Loop

```python
for symbol in universe:
    try:
        record = _scan_one(symbol, provider, config, today)
        if record:
            results.append(record)
    except DataUnavailableError:
        logger.warning(f"surge scan: {symbol} data unavailable, skipping")
    except Exception:
        logger.exception(f"surge scan: {symbol} unexpected error, skipping")
```

---

## BL-2: SurgeStore — JSONL 저장소

### BL-2.1: 저장 경로

- SurgeRecord: `steering/watch_surge/{date}.jsonl`
- SurgeAnalysis: `steering/watch_surge/{date}-analysis.jsonl`
- 디렉토리는 최초 write 시 자동 생성

### BL-2.2: write_records() — idempotent append

```python
def write_records(records: list[SurgeRecord]) -> int:
    """Append new records to date-named JSONL. Skip duplicates by (symbol, date)."""
```

1. 파일 경로: `steering/watch_surge/{records[0].date}.jsonl`
2. 기존 레코드가 있으면 `(symbol, date)` set 구성
3. 신규 레코드 중 기존 set에 없는 것만 append
4. 각 레코드는 한 줄 JSON (`model_dump_json()` + `\n`)
5. Atomic write: temp file에 write → `os.replace()` (stdlib atomic)
6. 반환: 실제 append된 레코드 수

### BL-2.3: read_records()

```python
def read_records(date: date) -> list[SurgeRecord]:
    """Read all surge records for a given date."""
```

- `steering/watch_surge/{date}.jsonl` 파일을 라인 단위로 읽음
- 각 라인을 `SurgeRecord.model_validate_json()` 로 파싱
- 파일이 없으면 빈 리스트 반환

### BL-2.4: append_analysis()

```python
def append_analysis(analysis: SurgeAnalysis) -> None:
    """Append a single analysis record. Validates (symbol, date) exists in records."""
```

1. `read_records(analysis.date)` 로 해당 일자 레코드 확인
2. `analysis.symbol` 이 레코드 목록에 존재하는지 검증 → 없으면 `ValueError`
3. `steering/watch_surge/{analysis.date}-analysis.jsonl` 에 atomic append
4. 동일 (symbol, date)에 대한 중복 분석은 마지막 것이 유효 (overwrite가 아니라 append — consumer가 최신 사용)

---

## BL-3: Agent Tools

### BL-3.1: surge_list

```
python -m src.agent.tools surge-list [--date YYYY-MM-DD]
```

1. `date` 없으면 오늘 날짜 사용
2. `SurgeStore.read_records(date)` 호출
3. 결과를 JSON 배열로 stdout 출력:
```json
[
  {
    "symbol": "AAPL",
    "direction": "up",
    "change_pct": 8.5,
    "volume_ratio": 2.3,
    "close_prev": 150.00,
    "close_today": 162.75
  }
]
```

### BL-3.2: surge_analyze

```
python -m src.agent.tools surge-analyze <SYMBOL> <DATE> <CAUSE> <LEADING_INDICATORS> <INFORMATION_GAP>
```

1. Arguments:
   - `SYMBOL`: 종목 티커
   - `DATE`: 거래일 (YYYY-MM-DD)
   - `CAUSE`: SurgeCause enum 값 (earnings/news/sector/technical/after_hours/mna/macro/unknown)
   - `LEADING_INDICATORS`: 선행 지표 텍스트 (따옴표로 감싼 단일 인자)
   - `INFORMATION_GAP`: 정보 갭 텍스트 (따옴표로 감싼 단일 인자)
2. `SurgeStore.append_analysis(SurgeAnalysis(...))` 호출
3. 성공 시 `{"status": "ok", "symbol": "...", "date": "..."}` JSON 출력
4. 해당 symbol이 그 날짜의 surge record에 없으면 에러 반환

---

## BL-4: Daemon Integration Flow

### EOD Flow (market close job)

```
Market Close Event
  │
  ▼
SurgeDetector.scan(universe, provider, config)
  │
  ▼
SurgeStore.write_records(records)
  │  → steering/watch_surge/YYYY-MM-DD.jsonl
  │
  ▼
EOD Review Turn 시작
  │  (agent가 surge-list tool로 데이터 조회)
  │  (agent가 surge-analyze tool로 분석 제출)
  ▼
EOD Review Turn 종료
```

### 설정 (config/settings.yaml)

```yaml
surge:
  threshold_pct: 7.0      # 급등/급락 판단 임계값 (%)
  min_volume: 0            # 최소 거래량 (0 = 제한 없음)
  # universe: null         # 대상 유니버스 (null = trading.symbols 사용)
```

---

## BL-5: DataProvider.get_daily_bar() 신규 메서드

기존 `DataProvider` 인터페이스에 일봉 조회 메서드 추가:

```python
def get_daily_bar(self, symbol: str, date: date) -> dict | None:
    """Return OHLCV dict for a single trading day, or None if unavailable."""
```

- yfinance 구현: `history(start=date, end=date+1day)` → 첫 행
- Alpaca 구현: `GetBarsRequest(symbol, TimeFrame.Day, start=date, end=date+1day)` → 첫 bar
- 실패/데이터 없음 → `None` 반환 (caller가 skip)
