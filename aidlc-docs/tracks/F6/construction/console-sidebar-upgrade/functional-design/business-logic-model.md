# F6 console-sidebar-upgrade · Business Logic Model (Functional Design)

## BLM-1 — 사이드바 폭: 정적→반응형 + 드래그 (FR-1)
**현재**: `routes/session/sidebar.tsx::sidebarWidth()`가 렌더 시 env 1회 읽기, `<box width={sidebarWidth()}>` 고정.
`routes/session/index.tsx:243` `contentWidth = dims.width − sidebar − 4`도 같은 정적 호출.

**변경**:
1. 폭을 **반응형 시그널**로 승격 (콘솔 컨텍스트, 예: `createSignal<number>` 또는 SolidJS context provider).
   초기값 = `loadWidth()`(E1: saved > env > 42).
2. `Sidebar`의 `width`와 `index.tsx`의 `contentWidth`가 **같은 시그널을 구독** → 한쪽 변경 시 양쪽 재레이아웃.
3. 사이드바 좌측에 **DragHandle**(E5) 추가 — **box에 `selectable={false}`**(critic #2; 없으면 텍스트 선택이 드래그를 가로챔):
   - `onMouseDown`: 활성 플래그 set + 시각 강조.
   - `onMouseDrag(e)`: `setWidth(clamp(dims.width − e.x, MIN=24, dims.width − MIN_CONTENT))`. 매 프레임 반영.
   - `onMouseDragEnd`: 활성 해제 + 디바운스 후 `saveWidth(width)`(E1).
   - **캡처 주의**: OpenTUI 캡처는 첫 drag의 hit-target에 잡힘 → 핸들에서 시작해야 캡처 보유. 라이브 스파이크(R1)로 확정.
4. **클램프 불변**: 24 ≤ width, 그리고 메인 콘텐츠 최소폭 보장(`dims.width − width ≥ MIN_CONTENT`). 터미널 리사이즈 시 재클램프.

## BLM-2 — 폭 영속화 (FR-1.1, Q1=A)
- `loadWidth()`: 상태파일 읽기 실패/부재/범위밖 → env, 그래도 없으면 42 (fail-safe, 콘솔 비충돌).
- `saveWidth(w)`: `onMouseDragEnd`에서 디바운스(예: 250ms) 저장. 원자적 쓰기(temp+rename) 권장.
- env(`AUTOSTOCK_SIDEBAR_WIDTH`)는 **저장값이 없을 때의 기본**으로만 작동(우선순위 유지).

## BLM-3 — 계정/라운드트립 발행 확장 (FR-2/3, Q2=A) — critic #1/#4/#5 반영
**(a) account (E2)** — `runtime.publish_snapshot._build()`(이미 워커, NFR-2)에서 **기존 `ps` 재사용 + 기존
`equity_log.snapshot(ps)` 재사용**(critic #5; 재구현 금지):
```
ps = broker.get_portfolio_state()              # 기존
account = equity_log.snapshot(ps)              # equity/cash/open_pnl/position_count (+positions) 재사용
self.channel.publish_snapshot({ ...기존..., "account": account, "round_trip": <아래> })
```
broker 추가 호출 없음(account는 기존 ps 재사용).

**(b) round_trip (E3)** — **별도 저빈도 잡**(critic #1, 사용자 B): `trades.jsonl`은 `_eod`에만 갱신되어 장중 빈 값이므로
워커가 30~60초마다 **fills/activities를 집계**:
```
fills = broker.get_fills(since=et_midnight)    # F3 정렬: get_fills 활동 포트 (저빈도 broker 호출 1종)
rt = summarize_today_round_trips(fills, now_et=now_et())   # match_round_trips 재사용
```
- `summarize_today_round_trips(fills, *, now_et)`: `match_round_trips(fills)` → **`filled_at` UTC→ET 변환**
  (`zoneinfo("America/New_York")`, critic #4) → 오늘 필터 → `{closed_count, win_rate, realized_pnl, as_of}`.
  거래 없음/소스 실패 → `{closed_count:0, win_rate:None, realized_pnl:0.0}`(빈 상태, fail-closed).
- **"broker 추가호출 0" 단정 폐기**: round_trip 위해 저빈도 fills 호출 1종 추가(NFR-3에 부하 제한 명시).
- **F3 정렬**: `get_fills`는 F3 intraday-redesign이 설계한 Alpaca activities 포트와 공유(둘 중 먼저 구현하는 쪽이 포트 제공).

## BLM-4 — 사이드바 표시 (FR-2/3/5)
`feature-plugins/sidebar/autostock.tsx` `View`:
- 신규 **계정 블록**(상단): `eq $… · cash $… · PnL ±… · N pos`. PnL은 부호별 색(FR-5).
- 신규 **성과 줄**: `today  W/L 60%  +$123  (5)` — 빈 상태면 "no closed trades".
- 기존 positions/orders/queued/events 유지. 섹션 헤더/구분으로 가독성 강화(FR-5).
- snapshot에 신규 필드 없으면(구버전 데몬) 해당 블록 **숨김**(fail-closed, 무회귀).

## BLM-5 — 깊은 모니터링 read 경로 (FR-4, Q3=A) — critic #3 반영
- **데몬 발행 잡**(신규, 저빈도): turns/decisions/log 요약을 `steering/monitor.json`(또는 뷰별 파일)로 원자적 발행.
  turns←turns.jsonl(최근 턴 비용/활동+오늘 누적), decisions←decisions.jsonl(최근 N), log←autostock.log(tail N, 시크릿 마스킹).
- **[critic #3 MED] "view 인자만 추가"는 틀림 — 3-파일 변경**:
  1. **`parser.ts`**: read 동사 화이트리스트(line 22)에 `turns`/`decisions` 추가(`log`/`status`는 이미 있음).
  2. **`filedrop.ts`**: `FileDrop`에 `monitor.json`(STEERING_DIR 경계 내) torn-safe 읽기 메서드 추가(현재 snapshot/events/commands만).
  3. **`steer-handler.ts`**: `handleSteerRead`가 **현재 verb를 무시하고 항상 snapshot 반환** → `draft.verb`로 분기
     (status→snapshot, turns/decisions/log→monitor 파일). (`log`도 지금은 무시되고 있음.)
- opencode CORE가 read tool=allow로 게이트(쓰기 권한 없음). 운영자 NL("show turn costs")→모델이 `steer_read{...}`.
- 전부 **read-only**; 토큰/쓰기 경로와 무관(NFR-1). 시크릿 미포함(NFR-2).

## BLM-6 — 데이터 흐름 요약
```
daemon(worker)  ── publish_snapshot ──▶ steering/snapshot.json ─(1.5s poll)─▶ sidebar(account/roundtrip/positions/events)
daemon(job)     ── publish_monitor  ──▶ steering/monitor.* ────(on-demand)──▶ steer_read{view} ─▶ operator(NL)
console(local)  ── drag ──▶ width signal ──▶ {Sidebar.width, contentWidth} + saveWidth ▶ ui.json
```
주문/스티어링 경로(NL→confirm→token→file-drop→RiskManager→Broker)는 **불변**.
