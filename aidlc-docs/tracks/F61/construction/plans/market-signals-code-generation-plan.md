# F61 Code Generation Plan — market-signals

> Construction 자율 진행([[feedback-autonomy-construction]]). 코드는 worktree `feat/F61`에서만.
> 체크박스는 구현하며 즉시 갱신.

## 순수 코어 (`src/signals/`, Tier 1 대상)
- [x] `records.py` — Mover, PeerGroup, PeerMap(+역인덱스), ReadThroughAlert, ImminentEarnings, MarketSignalBrief, MoverRow, EarningsRow (pydantic, 직렬화 round-trip)
- [x] `peer_map.py` — PeerMap.from_groups + `peers_of()` (순수)
- [x] `movers.py` — `detect_movers(rows, thresholds, universe)` (순수)
- [x] `readthrough.py` — `build_readthrough(movers, peer_map, universe, ...)` (순수)
- [x] `earnings_cal.py` — `select_imminent_earnings(rows, universe, held, peer_map, ...)` (순수)
- [x] `brief.py` — `assemble_brief(...)` + `MarketSignalBrief.to_prompt_text()` / `to_dict()` (순수)
- [x] `settings.py` — `SignalsConfig.from_settings(dict)` (임계·peer_groups·bellwether·sources·cache_ttl)

## 비순수 경계 (`src/signals/`)
- [x] `sources/alpaca_news.py` — AlpacaNewsProvider (alpaca-py NewsClient, 타임아웃)
- [x] `sources/finnhub_earnings.py` — FinnhubEarningsCalendar (`/calendar/earnings`, 타임아웃, 키부재 fail-honest)
- [x] `collector.py` — SignalCollector.collect(): 가격행(provider 재사용)+뉴스+실적 → 순수함수 → MarketSignalBrief. fail-honest·타임아웃·TTL 캐시
- [x] `eval_readthrough.py` — Tier 2 온디맨드 하니스(`python -m src.signals.eval_readthrough <scenario>`, LLM 호출, pytest 밖)

## 설정/배선
- [x] `config/config.py` — Settings에 `signals: dict = {}` + `finnhub_api_key: str = ""`
- [x] `config/settings.yaml` — `signals:` 블록(임계 시드, peer_groups R6, bellwether R7, sources R8)
- [x] `src/agent/tools/market.py` — `movers()`, `readthrough()`, `earnings_calendar()` 함수(주입형)
- [x] `src/agent/tools/__main__.py` — 서브커맨드 movers/readthrough/earnings_calendar 등록
- [x] `src/agent/prompts.py` — morning_research_prompt + multi_research_initial_prompt에 optional `signal_brief` prepend(하위호환)
- [x] `src/agent/orchestrator.py` — `signal_brief_provider` 주입 + 각 research 진입점에서 brief 조립·전달 (fail-honest)
- [x] 데몬 배선(`src/trading/modes/agent.py` 등) — SignalCollector 기반 provider 주입

## Tier 1 테스트 (`tests/signals/`)
- [x] `test_movers.py`, `test_peer_map.py`, `test_readthrough.py`, `test_earnings_cal.py`, `test_brief.py` (example)
- [x] `test_properties.py` — PBT(03 invariant), `test_records_roundtrip.py` — PBT(02), 도메인 생성기(07)
- [x] `scenarios/*.json` (S1~S5) + `test_scenarios.py` — 다유형 결정적 재현
- [x] `test_collector.py` — fake 소스로 fail-honest/degrade 검증
- [x] `test_tools_signals.py` — 툴 함수 주입 검증
- [x] `pytest.ini`/pyproject `addopts = -m "not manual"` — Tier 2 토큰 보호

## 검증
- [x] worktree에서 `pytest tests/signals` green + 기존 테스트 회귀 없음
- [x] (선택) 라이브 스모크 1회: Finnhub 실적 캘린더 실호출 형태 확인
