# F77 — Code Generation Plan (unit "stocktwits-sentiment")

**Base**: functional-design.md (승인 2026-06-13) · worktree `feat/F77`

## Part 2 실행 체크리스트

### A. 데이터/설정
- [x] A1. `src/signals/records.py` — `SentimentSnapshot`/`SentimentRecord`/`SentimentOutlier` + `MarketSignalBrief.sentiment_outliers`
- [x] A2. `src/signals/settings.py` — `SentimentConfig` 서브모델 (sweep/창/예산/베이스라인/임계값)
- [x] A3. `config/settings.yaml` — `signals.sentiment:` 블록 (기본값)

### B. 수집
- [x] B1. `src/signals/sources/stocktwits.py` — fetch_symbol + 관대 파싱 + RateLimited
- [x] B2. `src/signals/sentiment.py` — 순수 코어(집계/ratio/baseline/zscore/select_outliers) + JSONL append/load
- [x] B3. `src/signals/sentiment_sweep.py` — SentimentSweeper.sweep_tick (창/예산/백오프/부분 저장/예외 흡수)
- [x] B4. `src/trading/modes/agent.py` — 스윕 잡 등록 (enabled 시)

### C. 브리프
- [x] C1. `src/signals/collector.py` — 히스토리 read → 이상치 → brief (degraded 연동)
- [x] C2. `src/signals/brief.py` — assemble_brief 시그니처 + 렌더 섹션
- [x] C3. intraday 브리프 — 보유/워치 ∩ 이상치 라인 (src/agent/intraday/brief.py)

### D. 검증
- [x] D1. `tests/signals/test_sentiment*.py` — 순수 코어 PBT + 예제, 소스/스윕 가짜 HTTP, 예산 카운트, 브리프 렌더
- [x] D2. 전체 pytest 회귀
- [x] D3. 라이브 스모크 — 실제 5~10심볼 미니 스윕 → JSONL → 합성 히스토리로 이상치 → 렌더
