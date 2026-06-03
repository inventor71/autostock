# F6 console-sidebar-upgrade · Logical Components

## Python (데몬, `src/`)
- **`src/agent/equity_log.py::snapshot(ps)`** (재사용, critic #5) — account dict(equity/cash/open_pnl/position_count).
- **`src/core/trades.py::match_round_trips(fills)`** (재사용) — 라운드트립 매칭.
- **신규 집계 헬퍼** — `summarize_today_round_trips(fills, *, now_et) -> {closed_count, win_rate, realized_pnl, as_of}`
  (`filled_at` UTC→ET `zoneinfo` 변환 후 오늘 필터, critic #4). 순수 함수(PBT 후보).
- **브로커 `get_fills(since)` 포트** (신규, F3 정렬) — Alpaca activities(raw `/account/activities` GET, alpaca-py 0.43.2);
  BaseBroker no-op 기본 + Alpaca 구현. F3와 공유(먼저 구현하는 쪽이 제공).
- **`src/agent/steering/runtime.py`** (편집) —
  - `publish_snapshot._build()`: `account = equity_log.snapshot(ps)` 가산(broker 추가호출 0).
  - 신규 **저빈도(30~60초) 잡** `publish_round_trip()`: `get_fills` → `summarize_today_round_trips` → `round_trip` 가산.
  - 신규 `publish_monitor()`: turns/decisions/log 요약 → `steering/monitor.json` 원자적 발행.
  - `SteeringRuntime` 잡 등록부에 `add_seconds_job(publish_monitor, ...)` + `add_seconds_job(publish_round_trip, 30~60, ...)`.
- **monitor 요약 읽기 헬퍼** — turns.jsonl/decisions.jsonl(torn-safe, 기존 `jsonl.read_complete_lines` 재사용),
  autostock.log tail(시크릿 마스킹).

## TS (콘솔, `operator-console/cli/.../tui` + `operator-console/src`)
- **신규 폭 상태 모듈** (`routes/session/` 내 작은 모듈 또는 context) — `width` 시그널 + `loadWidth()`/`saveWidth()`
  (XDG `ui.json`, stdlib fs, 원자적 쓰기, 디바운스).
- **`routes/session/sidebar.tsx`** (편집) — `sidebarWidth()` 정적 → 시그널 구독; 좌측 **DragHandle** box 추가
  (`selectable={false}` + `onMouseDown/Drag/DragEnd`, critic #2).
- **`routes/session/index.tsx`** (편집) — `contentWidth` 메모가 폭 시그널 구독(재레이아웃); 폭 시그널은 `sidebarVisible`과
  독립 context, F5와 공유(critic #7).
- **`feature-plugins/sidebar/autostock.tsx`** (편집) — 계정 블록 + 성과 줄 + 섹션 헤더/PnL 색/빈 상태(FR-5);
  신규 snapshot 필드 부재 시 숨김(BR-8).
- **`operator-console/src/` 4-파일** (편집, critic #3) — `mcp-server.ts`(inputSchema), `parser.ts`(turns/decisions read 동사),
  `filedrop.ts`(monitor.json torn-safe 리더, 경계 내), `steer-handler.ts`(`handleSteerRead` verb 분기 — 현재 verb 무시·snapshot만 반환 수정).

## 테스트
- **Python**: `summarize_today_round_trips`(예시 + Hypothesis 불변 + **UTC→ET 경계** 케이스), `equity_log.snapshot` 재사용
  확인, publish_snapshot account 필드 + publish_round_trip(저빈도 fills) + publish_monitor 발행/원자성. `get_fills` no-op/Alpaca
  파싱 단위. 무회귀(기존 스위트).
- **TS(bun)**: `clampWidth`/`loadWidth` 우선순위·폴백, `handleSteerRead` **verb 분기**(status/turns/decisions/log)·부재 graceful,
  parser turns/decisions 동사. tsgo 타입체크.
- **라이브(사용자)**: `bun dev` 드래그 캡처 거동(R1) + 계정/성과 표시 + `steer_read` view + `get_fills` 페이퍼(R4).

## 변경 없음(불변)
- 주문/스티어링/토큰/RiskManager→Broker 게이트, 권한분리 훅, F4 contract 스키마(가산만), F5 소유 default-on/리브랜드.
