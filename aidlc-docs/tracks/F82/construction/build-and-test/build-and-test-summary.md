# F82 — Build & Test Summary

**대상**: Intraday 피처 자동 수집 — 유니버스 갭 백필(데몬 기동, 백그라운드) + 매 EOD append.
F80(Parquet store) 위 스택.

## 변경/신규 파일
- **신규** `src/data/intraday/auto.py` — `CollectionConfig`, `last_session_date`,
  `backfill_window`, `backfill_universe`, `collect_today`. 순수/주입식 오케스트레이션.
- `src/trading/modes/agent.py` — `__init__` 상태 필드, `_setup_intraday_collection()`
  (백그라운드 백필 스레드, config 게이트, alpaca/daemon provider 선택), `start()` 배선,
  `_eod()` EOD append 블록. 모두 best-effort(데몬/EOD 비차단).
- `config/settings.yaml` — `intraday_collection` 블록(enabled 기본 **true**, backfill_years 3,
  provider alpaca, timeframe 5m).
- **신규** `tests/intraday/test_auto_collect.py` — 13 테스트.

## 테스트 결과 (ALL GREEN — 대상 범위)
```bash
python -m pytest tests/intraday/test_auto_collect.py -q   # 13 passed
python -m pytest tests/intraday/ -q                        # 107 passed (전 intraday)
```
- `backfill_window`: 미저장→full / stale→증분 / 최신·전일→skip (경계 포함).
- `CollectionConfig.from_yaml`: 기본값/명시값.
- `backfill_universe`: 빈 store→기록, 재실행→skip(provider 미호출), 실패 종목 격리.
- `collect_today`: 날짜레인지 경로(end가 today 포함), 멱등(재실행 무중복).
- 데몬 배선: 게이트 off→미배선, on→백그라운드 스레드 백필 완료·store 채움, config 오류→fail-closed.

## 실데이터 라이브 스모크 (Alpaca, 실거래일 앵커)
- **백필 경로**: `collect(AAPL,MSFT, 2026-05-01~05-15, 5m)` → Alpaca 1909/1920 bars →
  각 10 세션 → Parquet 영속. 값 정상(AAPL ~$292–298, 실거래량).
- **EOD append 경로**: `collect_today(AAPL,MSFT, today=2026-05-14)` → 762/768 bars →
  각 4 세션(lookback 4d, today 포함) → upsert. last session = 2026-05-14 확인.
- 한계 메모: 주말/IEX 한정 `limit`-only 페치는 빈 응답 → `collect_today`를 **날짜레인지**로
  설계(스모크에서 발견·수정). 데몬 provider가 yfinance면 백필은 ~60일로 degrade.

## 전체 스위트 비고 (F82 비유발)
`pytest tests/ -q` → **1257 passed, 4 failed**. 4건 모두 F82 무관:
- `tests/signals/test_sentiment_sweep.py`(3) — base에서도 동일 실패(선존).
- `tests/test_health_publish.py`(1) — worktree에 gitignored `.env`/`settings.yaml` 부재 환경
  아티팩트(메인 통과).
(중간에 `test_watch` 1건이 새로 깨졌으나 — 신규 wiring 테스트의 `AGENT_JOURNAL_ROOT` env 누수
원인 — monkeypatch로 격리 복구, 현재 통과.)

## Extension Compliance
- Security Baseline: Disabled (N/A) — gitignored 비민감 시장 데이터, 신규 비밀 없음(기존 alpaca 키 재사용).
- Property-Based Testing: Disabled — 부수효과 오케스트레이션, example 기반 충분(피처/스토어 PBT는 F1/F80 보유).
