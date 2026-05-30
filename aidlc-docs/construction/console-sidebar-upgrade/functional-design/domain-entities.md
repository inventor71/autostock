# F6 console-sidebar-upgrade · Domain Entities (Functional Design)

> 단위: `console-sidebar-upgrade`. 대부분 **전이(transient) UI 상태 / read-view 확장**이며, 신규 영속 도메인
> 엔티티는 최소. FD 답변: Q1=A(콘솔 상태파일), Q2=A(둘 다 snapshot), Q3=A(read MCP 툴), Q4=A(핸들+드래그).

## E1 — SidebarWidthState (콘솔, 영속)
- **무엇**: 운영자가 드래그로 정한 사이드바 폭(열 수).
- **필드**: `width: int`(24 ≤ width ≤ 터미널폭 안전상한).
- **저장(Q1=A)**: 콘솔 전용 사용자 상태 파일 — XDG 기준 `${XDG_STATE_HOME:-~/.local/state}/autostock-console/ui.json`
  (또는 `~/.config/autostock-console/ui.json`; Code Gen에서 경로 1곳 확정). JSON `{ "sidebarWidth": <int> }`.
- **우선순위**: 저장값 > `AUTOSTOCK_SIDEBAR_WIDTH` env > 42(기본).
- **수명**: 드래그 종료(`onMouseDragEnd`) 시 디바운스 저장; 시작 시 1회 로드 → 반응형 시그널 초기화.
- **시크릿 아님** → 권한/SECURITY 영향 없음.

## E2 — AccountSummary (데몬 발행, read-view 확장 · Q2=A)
- **무엇**: 사이드바 상단 계정 요약. `snapshot.json`에 추가되는 블록.
- **필드**: `equity`, `cash`, `open_pnl`(미실현 합), `position_count`. (`PortfolioState`에서 도출:
  `models.py` equity/cash/position_count + Position.unrealized_pnl — critic 확인.)
- **출처**: `runtime.publish_snapshot`가 이미 워커에서 호출하는 `broker.get_portfolio_state()` (NFR-2 유지).
- **[critic #5 MED] 재사용**: 직접 재조립하지 말고 **기존 `src/agent/equity_log.py::snapshot(portfolio)`** 재사용
  (이미 equity/cash/open_pnl/position_count 동일 dict 생성) — 표시값과 equity 트랙레코드 일관.
- **수명**: 기존 snapshot 발행 주기에 동승(추가 broker 호출/스레드 없음).

## E3 — RoundTripSummary (데몬 발행, read-view 확장 · Q2=A)
- **무엇**: 오늘(ET-date) 청산 성과 요약. `snapshot.json`에 추가되는 블록.
- **필드**: `closed_count`, `win_rate`(0–1), `realized_pnl`(합), `as_of`(데이터 기준시각).
- **[critic #1 HIGH — 사용자 결정 B] 출처/신선도**: `trades.jsonl`은 `_eod`에만 갱신되어 장중 빈 값 → **워커가
  저빈도(30~60초)로 fills/activities를 집계**해 오늘 실현손익 산출. 라운드트립 매칭 `match_round_trips(fills)` 재사용.
- **[critic #4 MED] ET-date**: fill `filled_at`=UTC → `zoneinfo("America/New_York")` 변환 후 오늘 필터.
- **[F3 정렬]** fills 소스는 F3 intraday-redesign이 설계한 `get_fills`(Alpaca activities) 브로커 포트와 정렬/공유.
- **계산 위치**: 데몬 워커 측 순수 집계 함수(신규) `summarize_today_round_trips(fills, *, now_et)`. PBT 후보(승률∈[0,1], count≥0).

## E4 — MonitorView (FR-4, 데몬 발행 read 파일 · Q3=A)
- **무엇**: 사이드바 비상주, 온디맨드로 꺼내보는 깊은 모니터링 뷰. read MCP 툴이 반환.
- **종류(view)**: `turns`(턴 텔레메트리: 최근 턴 비용/활동·오늘 누적), `decisions`(최근 N건), `log`(agent log tail N줄).
- **출처/발행**: 데몬이 각 뷰의 **압축 요약**을 `steering/` 하위 read 파일로 발행
  (예: `steering/monitor.json` 단일 파일에 `{turns, decisions, log}` 또는 뷰별 파일 — Code Gen에서 1곳 확정).
  turns←`workspace/turns.jsonl`, decisions←`workspace/decisions.jsonl`, log←`logs/autostock.log`.
- **수명**: 저빈도 발행 잡(예: 5초 또는 기존 publish 동승). 전부 **read-only**, contract 경계(`STEERING_DIR`) 내부.

## E5 — DragHandle (콘솔, 전이 UI · Q4=A)
- **무엇**: 사이드바 좌측 경계의 얇은 수직 핸들(│). `onMouseDown`→`onMouseDrag`→`onMouseDragEnd` 캡처.
- **동작**: 드래그 중 `width = clamp(dims.width − e.x, 24, dims.width − MIN_CONTENT)`. 절대 `MouseEvent.x`(터미널
  0-기준 열, critic 확인) 사용.
- **[critic #2 HIGH] selectable=false 필수**: OpenTUI 기본 `selectable=true`라 핸들/텍스트 위 down은 **텍스트 선택**을
  시작해 이후 drag가 `onMouseDrag`에 도달하지 못한다. 핸들 box에 **`selectable={false}`** 부여(포크의 `logo.tsx`가
  동일 패턴 사용). 캡처는 down이 아닌 **첫 drag**의 hit-target에 잡히므로, 드래그가 핸들에서 시작·캡처를 보유하는지
  **라이브 스파이크로 검증**(R1) 후 확정.
- **상태 없음**: E1(폭 시그널)을 갱신만; 자체 영속 없음.

## 비-엔티티(명시적 제외)
- **권한/주문/토큰 모델 불변**: F4 E7 SteeringCommand / token / RiskManager→Broker 게이트는 손대지 않음(NFR-1).
- **사이드바 default-on / 리브랜드**: F5 소유 → F6 엔티티 아님.
