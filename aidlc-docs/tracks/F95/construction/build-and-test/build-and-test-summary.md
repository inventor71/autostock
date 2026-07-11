# F95 — Build & Test Summary

## Scope
심볼 클릭 → floating panel(SymbolOverlay)에 실시간 시세 항상 표시 + 현행(포지션/thesis/결정)
graceful. 데몬 per-instance REST warm-cache(`quotes.json`) + TUI 리더 + intervention 심볼 클릭화.

## Build
- **Python**: 신규 순수 모듈 `src/agent/steering/quotes.py`; `runtime.py`/`channel.py`/`agent.py` 배선. import/컴파일 정상(테스트 로드로 검증).
- **TS 콘솔**: `operator-console/cli`에서 `bun install` 후 `bun run typecheck` → **19/19 successful**(변경 패키지 `opencode`·`@opencode-ai/app` cache-miss 재컴파일 통과). 부트스트랩: `scripts/worktree-setup.sh F95 --ts` 또는 `PATH=~/.bun/bin:$PATH bun install && bun run typecheck`.

## Unit tests (`tests/test_steering_quotes.py`) — 8/8 pass
- QuoteBook: TTL 만료, price/error 상호배타, payload는 fresh-only.
- quote_candidates: 우선순위(held>orders>recent)·dedup·대문자화·cap·placeholder("?")·빈값 제거.

## Integration tests (bus 라운드트립) — 포함, pass
- `refresh_quotes` → `quotes.json`: 후보(decisions 유래) 중 AAPL 시세 기록, MSFT 조회 실패는 `{"error":"no_data"}`로 마킹(**fail-honest**, 무크래시), payload에 `provider`/`updated`/`published_at`.
- 후보 없음 → 빈 `quotes` 정상 publish.

## Regression — 146/146 pass
- `pytest -k "steering or quote or channel or runtime or agent_mode or trading"` → **146 passed, 0 failed**. 기존 steering channel/runtime 회귀 없음.

## Live smoke (real data) — PASS
- 실제 `create_data_provider(settings)` = **YFinanceProvider**로 `fetch_latest_prices(["AAPL","MSFT","NVDA"])` → 실시세 반환(AAPL 316.22 / MSFT 384.36 / NVDA 202.78), QuoteBook→`quotes.json` 직렬화 정상. `refresh_quotes`가 쓰는 데이터 플레인 end-to-end 검증.
- 미검증(문서 스모크로 이관): 라이브 데몬에서 2s 스케줄 잡이 실제로 `steering/quotes.json`을 주기 기록하는 것 + TUI 오버레이 실렌더 클릭 → post-merge-guide 체크리스트.

## Performance
- N/A(전용 성능 테스트 없음). 부하 관점은 NFR-6: candidate 상한 30 + 2s 배치(`fetch_latest_prices` 동시성) + TTL. yfinance 간헐 실패는 per-symbol fail-honest로 격리.

## Quality gates 결과
- [x] TS typecheck 19/19
- [x] Python unit 8/8 + integration
- [x] Regression 146/146
- [x] Live data-plane smoke PASS
- [x] fail-honest(조회 실패 시 무크래시, "시세 없음")
- [x] 인스턴스 격리(quotes.json = 인스턴스 steering, 지속 연결 없음)
- [x] 비회귀(turn/health 오버레이 무변경, intervention은 심볼 클릭만 추가)
