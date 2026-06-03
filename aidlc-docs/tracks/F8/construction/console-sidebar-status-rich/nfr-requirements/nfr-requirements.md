# F8 NFR Requirements (minimal)

- **결론: 신규 런타임 의존성 0.**
  - Python: `get_portfolio_state`/`get_open_orders`/`get_fills`(F3/F6)/`equity_log.snapshot`/`core.trades` 재사용. 미보유 주문심볼 가격 보충은 status.py가 쓰는 기존 alpaca data client(`StockHistoricalDataClient`)/provider 재사용.
  - TS: OpenTUI 텍스트 색 + 기존 `wrapMode`/드래그/`AUTOSTOCK_SIDEBAR_WIDTH`; stdlib만.
- **NFR-1 읽기전용**: 콘솔은 `snapshot.json`만 읽음(불변).
- **NFR-2 단일 워커 + 케이던스(확정)**: 발행 5s, PriceBook 슬로우잡 ~10–15s+캐시, recent_fills ~45s, 폴링 1.5s. 모든 브로커/data 접근 = 단일 워커.
- **NFR-3 성능**: 읽기전용 UI. 추가 비용 = 슬로우잡 가격/체결 fetch + 스냅샷 페이로드 소폭 증가. 부하시험 N/A.
- **NFR-4 fail-closed/하위호환**: 신규 필드 가산적, 부재 시 콘솔 숨김; fetch 실패 best-effort.
- **Security Baseline**: SECURITY-03(비밀값 없음)/SECURITY-15(fail-closed) 적용, 그 외 N/A. **PBT Partial**: pnl%/Δ%/역할 매핑/recent_fills 정렬·상위N 순수함수(Hypothesis, dev).
- **신규 질문 라운드 없음** — 결정은 D1~D4 + 케이던스 확정에서 도출됨.
- **NFR Design 이월**: PriceBook 캐시 자료구조/슬로우잡 정확 주기 상수, width-floor 정확값, recent_fills N, 5s 발행과 슬로우잡 캐시 접합.
