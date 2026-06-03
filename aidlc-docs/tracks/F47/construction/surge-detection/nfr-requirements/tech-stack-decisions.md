# surge-detection — Tech Stack Decisions

> Minimal Depth | 2026-06-03

## Decision: 0 New Runtime Dependencies

**Conclusion**: 신규 런타임 의존성 없음. 기존 스택으로 충분.

| Component | Technology | Status |
|-----------|------------|--------|
| Data models | `pydantic` (≥2.x) | ✅ 기존 사용 중 |
| HTTP/data fetch | `yfinance` + `alpaca-py` | ✅ 기존 DataProvider가 추상화 |
| Scheduling | `APScheduler` | ✅ 기존 daemon scheduler |
| Logging | `loguru` | ✅ 기존 사용 중 |
| File I/O | `stdlib` (`os`, `json`, `pathlib`) | ✅ |
| Agent tools | `stdlib` (`argparse`, `json`) | ✅ 기존 `__main__.py` CLI 패턴 |
| Testing | `pytest` + `hypothesis` (PBT Partial) | ✅ 기존 dev dependency |
| Config | `pydantic-settings` 또는 `yaml` | ✅ `config/settings.yaml` 기존 형식 |

---

## Decision: 설정 파일 위치

`config/settings.yaml`에 `surge:` 블록 추가:
```yaml
surge:
  threshold_pct: 7.0
  min_volume: 0
```

기존 `SurgeDetectionConfig` pydantic 모델이 로드.

---

## Decision: JSONL 형식

기존 F4 `src/agent/steering/jsonl.py`의 패턴 재사용:
- `read_complete_lines(path)` — torn-safe line reader
- `atomic_write_text(path, text)` — temp + os.replace
- `ByteCursor` — 필요시 cursor 기반 증분 읽기

---

## Decision: DataProvider 확장

기존 `src/data/base.py` `DataProvider` 인터페이스에 `get_daily_bar()` 추가:
- 기존 `get_bars()`는 multi-bar timeframe 기반 → 단일 일봉 조회에 적합하지 않음
- `get_daily_bar(symbol, date) -> dict | None` — 단순 명료한 인터페이스
- yfinance 구현: `Ticker.history(start, end)` 래핑
- Alpaca 구현: `GetBarsRequest` with `TimeFrame.Day`
