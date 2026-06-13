# F78 — Code Generation Plan (단일 단위: event-radar)

**Worktree**: `.claude/worktrees/F78` (branch `feat/F78`, base 01ced61)
**원칙**: additive, F61 earnings 경로 미러. 각 단계 완료 즉시 체크박스 갱신.

## Part 2 — 구현 단계

### A. 도메인 / pure core (PBT 대상)
- [x] A1. `records.py` — `IpoRow`(입력) + `ImminentIpo`(출력) 추가 (status Literal, price_low/high, est_value 등)
- [x] A2. `ipo_cal.py` (신규) — `select_imminent_ipos` pure (날짜창, withdrawn 제외, **universe 필터 없음**, 규모순 정렬+캡, in_universe/is_held 태깅)

### B. 소스 (I/O 경계)
- [x] B1. `sources/finnhub_ipo.py` (신규) — `FinnhubIpoCalendar.get_calendar` (`/calendar/ipo`, 키·타임아웃 재사용, price 문자열 파싱, 방어 파싱, transport 오류 raise)

### C. 설정
- [x] C1. `settings.py` — `SignalSources.ipo_provider` + `SignalsConfig.ipo_horizon_days/max_ipos`
- [x] C2. `config/settings.yaml` — `signals:` 블록에 ipo 디폴트 주석/키 (있으면)

### D. Brief 통합 (pure)
- [x] D1. `records.py` — `MarketSignalBrief.imminent_ipos` 필드 + `is_empty()` 반영
- [x] D2. `brief.py` — `assemble_brief` 인자 추가 + `to_prompt_text` "Imminent IPOs / catalysts" 섹션 ("awareness, NOT a buy menu" 라벨)

### E. Collector 통합 (I/O 경계)
- [x] E1. `collector.py` — `__init__` ipo_source 주입, `collect()` ipo_horizon_days 인자 + cache_key, `_imminent_ipos`, `assemble_brief` 호출 업데이트, `_build_ipo_source` + `from_settings` 와이어링

### F. Pull 도구 parity
- [x] F1. `market.py` — `ipo_calendar(collector, days=None)`
- [x] F2. `__main__.py` — `ipo_calendar` 서브파서 + dispatch
- [x] F3. `fixtures.py` — `MARKET_COMMANDS`에 `"ipo_calendar"` (NFR-4 하드)
- [x] F4. `prompts.py` — `_SIGNAL_TOOL_GUIDE`에 ipo_calendar 항목

### G. Prompt nudge
- [x] G1. `prompts.py` — `morning_research_prompt` step 2(Regime) nudge (Discovery 미변경)

### H. 테스트
- [x] H1. `tests/signals/test_ipo_cal.py` — pure core 예제 + **PBT**(정렬 안정성, 캡 경계, horizon 경계, withdrawn 제외, 멱등)
- [x] H2. record 직렬화 라운드트립 PBT (IpoRow/ImminentIpo)
- [x] H3. source 파싱 단위테스트(fake payload: price 범위/단일/누락 필드/withdrawn)
- [x] H4. collector 통합 테스트(fake ipo_source: 성공/실패→degraded/disabled, cache 공유)
- [x] H5. brief 렌더 + ipo_calendar 도구 + fixture 가로채기 테스트

### I. 검증 (Build & Test)
- [x] I1. 전체 signals 테스트 회귀 — 224 passed (F78 신규 포함). 사전 존재 F77 sentiment_sweep 3건 실패는 날짜 의존 테스트(F78 무관, base에서도 실패). evals 127 + signal_tools/screening/push_wiring 48 green
- [x] I2. 라이브 스모크 — 실제 Finnhub `/calendar/ipo` 1건(FCBM/NYSE/$101M/price 14-16) 파싱 정상, 스키마 확인. (CLI 풀경로는 worktree의 기존 `settings.trading.symbols` 설정로딩 quirk으로 미실행 — earnings_calendar도 동일, F78 무관)
