# F95 — Units of Work

> Track F95 · Units Generation. Application Design의 두 파티션을 유닛으로 확정.

## Unit 목록

### U1 — 데몬 Quote Warm-Cache Producer (Python, `src/`)
- **책임**: candidate 심볼 시세를 ~2s 배치 REST로 갱신 → `steering/quotes.json` 원자적 기록.
- **산출물**: `QuoteBook`(TTL 캐시), `SteeringRuntime._quote_candidates()`, `SteeringRuntime.refresh_quotes()`, `agent.py` 스케줄 등록, `quotes.json` writer, 단위 테스트.
- **소스**: `executor.data_provider`, `data.prices.fetch_latest_prices`, monitor decisions/intervention, broker positions/orders.
- **계약 생산자**: `steering/quotes.json` 스키마를 **먼저 확정**.

### U2 — TUI Quote Reader + Panel + Intervention 클릭 (TS, `operator-console/cli`)
- **책임**: quotes.json을 읽어 SymbolOverlay에 시세 항상 표시(+as-of), intervention 심볼 클릭화.
- **산출물**: `hooks/use-quote.ts`, `symbol-overlay.tsx`(Quote 섹션), `intervention-overlay.tsx`(클릭), `routes/session/index.tsx`(배선), 단위 테스트/typecheck.
- **계약 소비자**: `steering/quotes.json`.

## 의존성 & 순서
- **계약 우선**: U1이 `quotes.json` 스키마 확정·생산 → U2 소비. 스키마 후 **병렬 구현 가능**.
- **통합 지점**: 라운드트립(데몬이 쓴 quotes.json ↔ TUI 표시) + fail-honest(조회 실패→"시세 없음", 무크래시) + 비회귀(turn/health/intervention 오버레이).

## 구현 계획 (Construction 순서)
1. **U1 먼저** — quotes.json 스키마 락 + 데몬 프로듀서 + Python 단위테스트.
2. **U2** — 리더/패널/클릭 + typecheck + 렌더 테스트.
3. **Build & Test** — 통합 라운드트립 + fail-honest + 비회귀, post-merge guide(실사용 검증).

> 두 유닛 모두 소규모. Functional Design에서 남은 기술 결정(스키마 필드, 상한/윈도우, 갱신주기 기본, 캐시-미스 처리, 헤드라인 시세 vs 마킹가 표기) 확정 후 자율 구현.
