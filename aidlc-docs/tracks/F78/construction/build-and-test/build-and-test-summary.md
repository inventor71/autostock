# F78 — Build & Test Summary

**Branch**: feat/F78 (commit 5722d33, base 01ced61) · **Date**: 2026-06-13

## Build
순수 파이썬, 빌드 스텝 없음. 의존성 신규 추가 없음(`requests`는 기존). import sanity OK.

## Unit / Property tests
worktree에서 `venv/bin/python -m pytest`:

| 스코프 | 결과 |
|---|---|
| `tests/signals/` (신규 test_ipo_cal, test_finnhub_ipo + 확장 test_collector/test_brief/test_tools_signals) | **224 passed**, 3 failed |
| `tests/evals/` | **127 passed** |
| `tests/test_signal_tools.py` + `test_screening.py` + `signals/test_push_wiring.py` | **48 passed** |

**3 failed = 사전 존재 F77 결함(F78 무관).** `tests/signals/test_sentiment_sweep.py`의 3건
(`test_happy_path_persists_all`, `test_symbol_failure_skipped_others_collected`,
`test_rate_limited_aborts_but_persists_partial`)은 **base(main, src 미변경)에서도 동일 실패**.
원인: `sweep_tick()`이 실제 clock(오늘 6/13)으로 날짜 파일에 기록하는데 테스트는 고정 과거날짜
(`ET_NOON`=6/12)로 `load_recent` → 못 찾음. 날짜 의존 시한폭탄(6/12까진 통과). → **별도 F77 후속 버그**.

### F78 신규/확장 테스트 (전부 green)
- `test_ipo_cal.py`: 예제(horizon 경계/withdrawn 제외/universe 비필터+태깅/규모순+캡/심볼정규화)
  + **PBT**(불변식: 캡·in-window·non-withdrawn·규모 단조감소·None 후순위 / 멱등 / IpoRow·ImminentIpo 직렬화 라운드트립)
- `test_finnhub_ipo.py`: 문서 스키마 파싱 / price-range·단일 / unmapped status→unknown /
  누락·비-dict 행 skip / HTTP 오류 raise / 빈 payload / `_parse_price_range` 헬퍼
- `test_collector.py`: ipo happy(비-universe-필터) / 고유 horizon / disabled / failure→degraded / per-call override 비-config-변경
- `test_brief.py`: IPO 섹션 렌더 + "NOT a buy menu" 라벨
- `test_tools_signals.py`: `ipo_calendar` 도구 + days override 전달
- `test_tools_fixtures.py`: `ipo_calendar` ∈ MARKET_COMMANDS fixture 가로채기(NFR-4)

## Integration / Live smoke (NFR-1/4 + 외부 통합)
- **라이브 Finnhub**: 실제 `/calendar/ipo` 호출 1건(FCBM, NYSE, expected, est ~$101M,
  price 14.0-16.0) — symbol/name/date/exchange/status/est_value/price-range 파싱 정상,
  스키마(`ipoCalendar` 키 + 필드) 라이브 확인. fail-honest(키 없으면 `ipo:disabled`,
  HTTP 오류 `ipo:finnhub`) 단위테스트로 커버.
- **알려진 환경 quirk**: worktree CLI 풀경로(`ipo_calendar`/`earnings_calendar` 둘 다)는
  기존 `settings.trading.symbols` 설정로딩 이슈로 미실행 — **F78 무관**(F61 도구 동일), prod 데몬 env에선 정상.

## NFR / Extension 준수
- NFR-1 fail-honest ✓ / NFR-2 timeout(earnings와 동일 connect/read, 단일 HTTP) ✓ /
  NFR-3 cache 공유(ipo_horizon cache_key 포함) ✓ / NFR-4 eval seam ✓ /
  Security Baseline: 키 env-only·비노출·방어 파싱 ✓ / PBT Partial: pure core+직렬화 ✓

## 판정
F78 변경분 **green**. 회귀 없음(3 실패는 사전 존재 F77 건). **merge-awaiting** 설정.
