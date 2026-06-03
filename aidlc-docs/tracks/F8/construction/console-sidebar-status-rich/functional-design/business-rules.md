# F8 Functional Design — Business Rules (light)

- **BR-1 읽기전용 경계**: 콘솔은 `snapshot.json`(+ monitor.json)만 읽음. 브로커/data 직접 접근 금지(NFR-1, F4/F6 불변).
- **BR-2 가산적·하위호환**: 모든 신규 필드(positions.current_price/market_value/unrealized_pnl, open_orders.side/order_type/current_price, account.invested, recent_fills)는 가산적. 콘솔은 필드/블록 부재 시 **숨김**(렌더 깨짐 금지).
- **BR-3 단일 워커**: 모든 브로커/data 접근은 단일 CommandBus 워커(NFR-2). 신규 PriceBook 보충 fetch·recent_fills fetch도 워커 잡.
- **BR-4 best-effort fail-closed**: 가격/체결 fetch 실패 → 해당 부분만 생략(Δ 공란/블록 숨김), 스케줄러로 예외 전파 금지(NFR-4). 가격 fetch 실패가 보유가격·스냅샷 발행을 막지 않음.
- **BR-5 케이던스(확정)**: 발행 5s(보유가격/주문필드/invested 추가콜 0) · PriceBook 슬로우잡 ~10–15s+캐시(이미 가격 있는 심볼 제외) · recent_fills ~45s · 콘솔 폴링 1.5s. ms 금지.
- **BR-6 색(D3)**: 손익/체결-side/Δ-방향만 green(≥0)/red(<0)+▲▼. 역할/헤더/심볼 색은 v1 제외.
- **BR-7 레이아웃(D2)**: 행은 기본 폭에서 잘림 없는 **1줄 압축**; 폭 확대 시 **word-wrap**으로 전체 노출; **최소 폭 floor** 적용(핵심 필드 항상 가독). 기존 `AUTOSTOCK_SIDEBAR_WIDTH`(24–120)/드래그 핸들/`wrapMode="word"` 위에 구축.
- **BR-8 데몬 재시작**: 신규 블록은 데몬이 새 스냅샷을 발행해야 보임. 머지 후 `main.py --mode agent --steering` 재시작 필요(F6 GOTCHA 동일).
- **BR-9 SECURITY**: 스냅샷/로그에 비밀값 없음 — 가격/수량/심볼만(SECURITY-03). 가격 fetch 예외는 fail-closed(SECURITY-15).
- **BR-10 계약 권위**: snapshot 스키마는 Python(`publish_snapshot`)이 권위. TS `schema.ts` 미러 + 크로스랭귀지 contract(F4 Phase4 패턴) 갱신.
