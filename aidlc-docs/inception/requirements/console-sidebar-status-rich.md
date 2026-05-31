# F8 요구사항 — Operator Console 사이드바: status.py 수준 정보 + 색 가독성

- **트랙**: F8 (Console Sidebar — status.py-rich Data & Color)
- **시작**: 2026-05-31
- **분류**: Brownfield, 기존 F4/F6 콘솔 위에 증분. UI 기능 변경.
- **깊이**: Standard. **리스크**: Medium (데몬 발행 페이로드 확장 + 콘솔 UI 변경; 주문심볼 가격 보충 fetch가 유일한 신규 네트워크 동작).

## 1. 의도 (사용자 원문)
> "현재 사이드바가 정보가 좀 부족하고 색으로 가독성을 올려야할듯. `scripts/status.py` 에서 보여주던 풍부한 정보를 사이드바로 좀 옮겨올 수 있을까?"

`scripts/status.py`(읽기전용 대시보드)가 보여주는 4개 블록의 풍부함을 operator-console 사이드바(`autostock.tsx`)로 이식하고, status.py와 동일한 손익 green/red+화살표 색을 입혀 가독성을 올린다.

## 2. 현재 상태 (코드 그라운딩)
- **사이드바(F6, `feature-plugins/sidebar/autostock.tsx`)**: run-state/market, 보유(심볼+수량만, 예: `AAPL 10`), 주문(예: `META lim=720`/`META stop=605` — 역할·현재가·Δ 없음), account 블록(eq/cash/pnl), round-trip, event 피드. `snapshot.json`을 ~1.5s 주기로 읽는 **읽기 전용**(NFR-1). 폭은 `AUTOSTOCK_SIDEBAR_WIDTH`(기본 42, 24–120) + events는 `wrapMode="word"`.
- **데몬 발행(`src/agent/steering/runtime.py::publish_snapshot`)**:
  - `positions`: `{qty, avg_entry_price}` — **현재가/평가손익 없음**.
  - `open_orders`: `{symbol, order_id, stop_price, limit_price}` — **side/역할/현재가/Δ 없음**.
  - `account`(`_account_block`): `{equity, cash, open_pnl, position_count}` — **invested 없음**.
  - `fills`: cursor 이후 *새* 체결만(웨이크용, 일시적) — status.py식 "최근 체결 목록" 아님.
- **status.py가 더 보여주는 것**: 포지션 `Avg/Now/P&L$/P&L%`(색); 주문 `Side/Role(entry|stop-loss|take-profit)/Trigger/Now/Δ%`(색); Recent fills `When/Side/Qty/Sym/Fill`; summary `invested/open P&L/positions`. 가격은 보유분 `current_price` 재사용 + 미보유 주문심볼은 data API로 보충(`_latest_prices`).

## 3. 확정 결정 (concretizing 답변 2026-05-31)
- **D1 — 범위**: 네 블록 **전부** 이식(보유 상세 · 주문 상세 · 최근 체결 · 요약 지표).
- **D2 — 좁은폭 레이아웃**: **1줄 행, 데이터 손실 없이 짧게.** 사이드바를 **드래그로 넓히면 word-wrap**으로 전체가 보이도록. **최소 드래그 칸수(width floor)** 를 정해 1줄 행이 가독 한계 아래로 잘리지 않게 한다.
- **D3 — 색**: **손익 green/red + ▲▼ 화살표**(status.py 동일 팔레트). 과한 테마/역할색은 v1 제외.
- **D4 — 가격/Δ 데이터**: status.py 방식 — **보유 포지션 `current_price` 재사용 + 미보유 주문심볼만 data API로 보충 fetch.** 정확하지만 발행 경로에 가격 fetch가 추가됨(아래 NFR-2에서 다룸).

## 4. 기능 요구사항 (FR)
- **FR-1 보유 상세**: 보유 행이 `심볼 · 수량 · 평단 · 현재가 · 평가손익$ · 평가손익%`를 표시(D3 색). *발행 확장*: `snapshot.positions[sym]`에 `current_price`, `market_value`, `unrealized_pnl` 추가(전부 `get_portfolio_state()`의 `PortfolioState`에 이미 존재 → 추출만). %는 콘솔에서 `current/avg-1`로 파생.
- **FR-2 주문 상세**: 미체결 주문 행이 `심볼 · side · 역할 · 트리거 · 현재가 · Δ%`(트리거까지 거리)를 표시(D3 색). 역할 로직은 status.py `_order_role` 미러(BUY→entry, STOP/STOP_LIMIT→stop-loss, 그 외→take-profit). *발행 확장*: `open_orders[*]`에 `side`, `order_type`(역할 파생용), `current_price` 추가. 현재가는 보유분 재사용 + 미보유 심볼 보충(D4).
- **FR-3 최근 체결**: status.py식 최근 체결 목록(최근 N≈8) `시각 · side · 수량 · 심볼 · 체결가`(D3 색). *발행 확장*: 슬로우 케이던스로 `recent_fills` 목록 발행(F3/F6 `get_fills` 재사용, ts 내림차순 상위 N). 기존 일시적 `fills`(웨이크용)와 **별개**.
- **FR-4 요약 지표**: account 블록에 `invested`(=Σ market_value) 추가. `open_pnl`/`position_count`는 기존 재사용.
- **FR-5 색/가독성**: 평가손익·평가손익%·체결 side·주문 Δ 방향을 green(≥0)/red(<0) + ▲/▼로. status.py `_pnl_markup` 시각언어를 TUI에 이식.
- **FR-6 레이아웃·폭**: 각 행은 기본 폭에서 **잘림 없는 1줄 압축**; 폭이 넓어지면 **word-wrap**으로 전체 노출; **최소 폭 floor**(예: ≥36칸; NFR Design에서 확정) 적용해 핵심 필드가 항상 읽히게. 기존 `AUTOSTOCK_SIDEBAR_WIDTH`/드래그 리사이즈/`wrapMode` 메커니즘 위에 구축.

## 5. 비기능 요구사항 (NFR)
- **NFR-1 읽기전용 경계 불변**: 콘솔은 `snapshot.json`만 읽음. 브로커 직접 접근 없음(F4/F6 불변).
- **NFR-2 단일 워커 + 베스트-에포트 가격 fetch + 케이던스(확정 2026-05-31)**: 모든 브로커/data 접근은 단일 CommandBus 워커에서. 실패해도 스케줄러로 예외 전파 금지.
  - **확정 케이던스 (기본값 유지)**: 콘솔 폴링 **1.5s**(불변), 스냅샷 발행 **5s**(불변).
  - 보유 현재가·평가손익(FR-1) + 주문 side/역할/트리거(FR-2): 이미 5s 발행 때 호출되는 `get_portfolio_state()`/`get_open_orders()`에서 추출 → **추가 네트워크 0, 5s 갱신**.
  - 미보유 주문심볼 현재가·Δ(FR-2/D4): **별도 슬로우잡 ~10–15s + 캐시**(이미 가격 있는 심볼 제외). 5s 발행은 캐시 값을 접합만 함.
  - 최근 체결(FR-3): **~45s**(round_trip 잡과 동급), `get_fills` 재사용.
  - ms 단위 불가/불요(브로커 레이트리밋, 기계적 OCO, 단일 워커 경합). 정확 주기값(10s vs 15s 등)은 NFR Design에서 상수 확정.
- **NFR-3 신규 런타임 의존성 0**: 가격 보충은 status.py처럼 기존 alpaca data client/provider 재사용.
- **NFR-4 가산적·하위호환·fail-closed**: 모든 신규 필드는 가산적. 콘솔은 필드 부재 시 해당 블록/컬럼 숨김(F6 BR-8 선례). 머지 전 데몬은 구 스냅샷을 발행 → 콘솔이 신규 표시를 안 함(정상). **데몬 재시작 필요**(F6 GOTCHA 동일).
- **NFR-5 성능**: 읽기전용 UI. 추가 비용 = 슬로우 케이던스 가격/체결 fetch 1~2건 + 스냅샷 페이로드 소폭 증가. 별도 부하시험 N/A.

## 6. 통합 표면 / 영향 파일 (예비)
- **데몬(Python)**: `src/agent/steering/runtime.py`(`publish_snapshot` positions/open_orders 확장, `_account_block` invested, 신규 `recent_fills` + 미보유 심볼 가격 보충 helper). 가능 시 `core/trades`/`equity_log` 재사용. status.py의 `_order_role`/`_latest_prices` 로직을 공유 유틸로 추출 검토.
- **콘솔(TS, 서브모듈 `operator-console/cli/.../feature-plugins/sidebar/autostock.tsx`)**: 보유/주문/최근체결/요약 렌더 확장 + green/red·▲▼ + 1줄압축/word-wrap + width floor. 스키마 미러(`operator-console/src/schema.ts`)에 신규 필드 반영.
- **계약**: snapshot 스키마가 권위(Python). TS 미러 + 크로스랭귀지 contract(F4 Phase 4 패턴) 갱신 검토.

## 7. 익스텐션 (Extension Configuration)
- **Security Baseline = Enabled** (프로젝트 기본). 적용: SECURITY-03(스냅샷/로그에 비밀값 없음 — 가격/수량만), SECURITY-15(가격 fetch fail-closed). 대부분 N/A(로컬 데몬, 외부 노출 없음).
- **Property-Based Testing = Partial**. 후보: 평가손익%·Δ% 순수 계산, 역할 매핑, recent_fills 정렬/상위 N. Hypothesis(dev).

## 8. 미해결/설계 이월 (NFR Design 이후 결정)
- 가격 보충 fetch 케이던스/캐시(5s 발행 인라인 vs 슬로우잡 분리) 및 `recent_fills` 케이던스.
- width floor 정확값 + word-wrap 동작(현 `wrapMode="word"`/드래그 핸들과 정합).
- status.py 로직 공유 유틸 추출 범위(중복 vs 공유).
- User Stories 실행 여부(단일 운영자 도구 → F2~F7 선례상 SKIP 유력) — Workflow Planning에서 확정.

## 9. 수용 기준 (AC, 상위)
- AC-1 보유 행에 평단/현재가/평가손익$/% 표시 + 손익 green/red·▲▼.
- AC-2 주문 행에 side/역할/트리거/현재가/Δ% 표시(미보유 심볼도 현재가/Δ 보충).
- AC-3 최근 체결 목록(시각/side/수량/심볼/체결가) 표시.
- AC-4 요약에 invested 포함.
- AC-5 기본 폭에서 행이 잘리지 않고, 드래그로 넓히면 wrap으로 전체 노출, 최소 폭 floor 적용.
- AC-6 신규 필드 부재 시 콘솔이 깨지지 않고 해당 블록만 숨김(하위호환).
- AC-7 콘솔은 여전히 `snapshot.json`만 읽고 브로커 직접 접근 없음(NFR-1).
