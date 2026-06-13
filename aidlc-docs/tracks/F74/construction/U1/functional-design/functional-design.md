# U1 Functional Design — tools fixture/record 모드

## 설계 정제 (R1): DataSources 팩토리 → 디스패치-레벨 인터셉트
Application Design C1은 "DataSources 팩토리로 모든 결선 주입"이었다. 코드 정밀 확인 결과:
- `market.py`의 8개 함수는 **이미 주입 파라미터를 보유** (`ticker_factory=None`,
  `news_provider=None`, `provider=None` — `market.py:153,165,225,319,384,427,463,496`).
  설계가 가정한 "seam 신설"은 불필요.
- 따라서 fixture의 진짜 요구는 "업스트림 객체 모킹"이 아니라 **agent가 보는 최종 tool 출력의
  통제**다. yfinance `Ticker` 객체 프로토콜(.info/.insider_transactions/...)을 흉내내는 것보다
  `__main__.main()`의 **디스패치 직전에 한 번 인터셉트**하는 쪽이:
  (a) 단일 chokepoint 보장이 더 강함 — market-data 명령은 어떤 경로로도 실데이터에 닿을 수
  없음 (critic 1R/2R의 "조용한 폴백" 우려 원천 차단),
  (b) fixture 계약 = **최종 출력 JSON 스키마** — 시나리오 작성자가 실제 tool 출력을 보고
  그대로 작성/record 캡처 가능,
  (c) 프로덕션 결선 코드 변경 0 (동작 보존이 자명).
- C1의 "단일 주입 팩토리" 의도(하나의 통제 지점)는 디스패치 인터셉트가 그대로 달성한다.
  **프로덕션 영향은 `__main__.py`의 인터셉트 훅 추가뿐.**

## 명령 분류 (코드 전수 — `__main__.py:56-199`)
- **MARKET_COMMANDS (fixture/record 대상, 15개)**: quote, indicators, fundamentals, news,
  scoreboard, earnings, insider, analyst_upgrades, institutional, short_data, macro, account,
  movers, readthrough, earnings_calendar
- **WORKSPACE_COMMANDS (통과, 4개)**: lesson, watch, surge-list, surge-analyze — sandbox
  workspace에 정당하게 읽기/쓰기 (`AGENT_JOURNAL_ROOT`로 라우팅, 기존 메커니즘).

## 데이터 모델 — fixture 디렉터리 포맷
```text
<fixture_dir>/
├── quote.json        # {"AAPL": {…tool 출력…}, "MSFT": {…}}
├── account.json      # {"_": {…}}   ("_" = 심볼 없는 명령의 키)
├── macro.json        # {"_": {…}}
└── …                 # 명령당 1파일, 없는 명령/키 = fixture 미정의
```

## 동작 규칙
1. `AUTOSTOCK_TOOLS_FIXTURE_DIR` 설정 + cmd ∈ MARKET_COMMANDS →
   `FixtureStore.get(cmd, key)` 반환 (key = symbol 또는 "_"). **실데이터 코드는 실행되지 않음.**
2. fail-honest: 파일/키 미존재 → `{"error": "fixture_missing", "tool": cmd, "key": key,
   "fixture_dir": …}` 를 stdout JSON으로 (exit 0 — agent가 읽고 적응 가능, 루브릭 관찰 대상).
3. `AUTOSTOCK_TOOLS_RECORD_DIR` 설정(+fixture 미설정) → 실데이터 계산 후
   `RecordingStore.save(cmd, key, out)` — 동일 포맷으로 머지 저장 (원자적 replace).
   둘 다 설정 시 fixture 우선, record 무시 (경고 stderr).
4. env 미설정 → 기존과 100% 동일 경로 (동작 보존).

## 비즈니스 룰 / 불변식 (PBT 대상)
- **INV-1 (round-trip, PBT-02)**: 임의의 JSON-직렬화 가능 출력 `o`에 대해
  `save(cmd,k,o)` 후 `get(cmd,k) == o`.
- **INV-2 (no-silent-substitute, PBT-03)**: `get(cmd,k)`는 저장된 객체 그대로 또는
  `fixture_missing` 에러 객체만 반환 — 다른 키/명령의 값이 새지 않음.
- **INV-3**: fixture 모드에서 MARKET_COMMANDS의 어떤 명령도 네트워크 코드(provider/broker
  팩토리)를 import/호출하지 않음 (테스트: 팩토리 monkeypatch 후 미호출 assert).

## 산출물
- `src/agent/tools/fixtures.py` (신규): MARKET_COMMANDS, FixtureStore, RecordingStore
- `src/agent/tools/__main__.py` (수정): 디스패치 인터셉트 + record 훅
- `tests/evals/test_tools_fixtures.py` (신규): 단위 + PBT (hypothesis, 제너레이터는
  `tests/evals/generators.py`에 중앙화 — PBT-07)
