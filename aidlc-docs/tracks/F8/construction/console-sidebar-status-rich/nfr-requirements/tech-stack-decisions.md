# F8 Tech Stack Decisions

| 관심사 | 결정 | 근거 |
|---|---|---|
| 보유 현재가/손익 | `PortfolioState.positions[*]`에서 추출(이미 5s 발행 때 fetch) | 추가콜 0 |
| 미보유 주문심볼 가격 | 기존 alpaca `StockHistoricalDataClient`(status.py와 동일), 워커 슬로우잡 + 인메모리 캐시 | 신규 의존성 0, 레이트리밋 회피 |
| 최근 체결 | `broker.get_fills`(F3/F6 FillEvent) 재사용, ts desc top-N | trades.jsonl은 EOD-only라 부적합(F6 교훈) |
| invested | `Σ market_value` | status.py 동일 |
| 역할/색/Δ 파생 | 콘솔(TS) 순수 함수 | 데몬은 원시값만 발행(계약 단순) |
| 색 | OpenTUI 텍스트 green/red + ▲▼ | status.py `_pnl_markup` 시각언어 |
| 레이아웃 | 1줄 압축 + `wrapMode="word"` + width-floor | D2; F6 events 패턴 검증됨 |
| 계약 | Python snapshot 권위 + TS `schema.ts` 미러 + 크로스랭귀지 contract | F4 Phase4 패턴 |

- 빌드: Python worktree off `main` + 서브모듈 `operator-console/cli` TS 편집(bun 테스트).
- 0 new runtime deps (Python/TS 양쪽).
