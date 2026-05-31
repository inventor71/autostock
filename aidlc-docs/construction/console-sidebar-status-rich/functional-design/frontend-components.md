# F8 Functional Design — Frontend Components (사이드바, `autostock.tsx`)

기존 F6 사이드바(run-state/market · account · round-trip · positions · pending · events)를 확장. 콘솔 측 순수 파생(역할/색/Δ/pnl%)은 BLM-1~3.

## FC-1 — 보유 블록 (PositionRow, FR-1)
- 기본 폭: 1줄 압축. 예 `AAPL 10 @182.40  ▲+1.2%` (qty·평단·pnl%, 색은 pnl 방향).
- 폭 확대(word-wrap) 시: 평가손익$·market_value 등 추가 필드까지 노출.
- 손익 색/▲▼(BLM-2). 보유 없음 → 빈 상태 문구.

## FC-2 — 주문 블록 (OrderRow, FR-2)
- 1줄 예 `META stop 605  ▼-2.1%` (심볼·역할·트리거·Δ; side는 역할로 충분, 폭 넓으면 추가).
- 역할 라벨(BLM-1), Δ 색(방향). current 없는 심볼 → Δ 공란.
- 주문 없음 → 숨김/빈 상태.

## FC-3 — 최근 체결 블록 (RecentFill, FR-3) — 신규
- 상위 N(8), 1줄 예 `15:04 BUY 5 META @631.20` (시각·side색·수량·심볼·체결가).
- `recent_fills` 부재/빈 → 블록 숨김(BR-2).
- 기존 events 피드와 별개(events=상태이벤트, 이건 구조화 체결).

## FC-4 — 요약(account) 블록 (FR-4)
- 기존 eq/cash/pnl/positions에 **invested** 추가. open_pnl 색(BLM-2).

## FC-5 — 레이아웃·폭 (BR-7/D2)
- 행 렌더는 `wrapMode="word"`로 폭 내 전체 표시(잘림 제거; F6 events에서 검증된 패턴).
- **최소 폭 floor** 도입: 드래그/`AUTOSTOCK_SIDEBAR_WIDTH` clamp 하한을 24 → **floor(예 36)**로 올려 1줄 행 핵심 필드가 항상 가독. (정확값 NFR Design.)
- 색: OpenTUI 텍스트 색(green/red) — 기존 사이드바 색 사용처와 동일 토큰.

## 데이터 출처 (요약)
`snapshot.json` → `{positions{...현재가/손익}, open_orders[{side,order_type,current_price,...}], account{...invested}, recent_fills[...]}`. 전부 데몬 발행(NFR-1).
