# F61 Build & Test Summary — market-signals

## 빌드
순수 Python 추가(신규 `src/signals/` 패키지 + 에이전트 배선). 신규 런타임 의존성 없음
(`alpaca-py`, `yfinance`, `requests`(transitive), `hypothesis`(기존 dev dep) 사용). 빌드 단계 불필요 —
import 가능하면 동작.

```bash
# (worktree에서) 컴파일 무결성
python -m py_compile main.py config/config.py \
  src/agent/orchestrator.py src/agent/prompts.py \
  src/agent/tools/market.py src/agent/tools/__main__.py \
  src/signals/*.py src/signals/sources/*.py
```

## 테스트 (Tier 1 — 자동, 토큰 0)
```bash
python -m pytest tests/signals -q          # 신규 시그널 스위트 (51 tests)
python -m pytest -q                         # 전체 회귀 (838 passed)
```
- 유닛: `test_movers / test_peer_map / test_readthrough / test_earnings_cal / test_brief`
- PBT(Partial — Hypothesis): `test_records_roundtrip`(PBT-02), `test_properties`(PBT-03, 도메인 생성기 PBT-07, 시드 재현 PBT-08)
- 다유형 시나리오 코퍼스: `test_scenarios` + `scenarios/S1..S5.json` (진양성 S1/S2/S3 + 오탐0 S4/S5)
- 통합(경계): `test_collector`(fail-honest/degrade, 캐시), `test_tools_signals`(툴 dict 출력)

## 테스트 (Tier 2 — 온디맨드, 토큰 듦, **CI 미포함**)
```bash
python -m src.signals.eval_readthrough S1 --brief-only   # LLM 없이 브리프만
python -m src.signals.eval_readthrough S1                 # 실제 에이전트 판단 (토큰)
```
- NFR-7: 기본 `pytest`는 `-m "not manual"`로 토큰 0 보장. eval 하니스는 `tests/` 밖.

## 라이브 스모크 (검증 완료 2026-06-05)
- `python -m src.agent.tools readthrough AVGO` → 실제 config 피어맵 22개 유니버스 피어 반환 ✅
- Finnhub 실호출: 키 작동, 향후 7일 114건 파싱 ✅
- S1 브리프 렌더: `AVGO -15.2% (guidance miss) → NVDA, AMD, MRVL, QCOM` ✅ (사용자가 놓쳤던 시나리오 재현)

## 결과
- **Tier 1: 51 passed / 전체 838 passed, 회귀 없음.**
- fail-honest·타임아웃 바운드·토큰 보호 검증 완료.
- FINNHUB_API_KEY는 `.env`에만(코드 미포함, gitignore). 키 부재 시 실적 캘린더만 degrade.

## 검증 매트릭스 (요구사항 → 테스트)
| 요구 | 검증 |
|---|---|
| FR-1 무버 | test_movers, test_properties, S1~S5 |
| FR-2 뉴스(Alpaca) | test_collector(cause_hint), 라이브(Alpaca 키 보유) |
| FR-3 read-through | test_readthrough, test_properties, S1/S2/S3(+), S4(−) |
| FR-4 실적 캘린더 | test_earnings_cal, Finnhub 라이브 스모크 |
| FR-5 push+툴 | test_tools_signals, prompts/orchestrator 회귀, S1 브리프 렌더 |
| FR-5a/Tier2 | eval_readthrough(--brief-only 검증), NFR-7 addopts |
| NFR-1 fail-honest | test_collector(news/earnings/scoreboard 실패 degrade) |
| NFR-4 결정성 | 순수함수 유닛 + PBT |
