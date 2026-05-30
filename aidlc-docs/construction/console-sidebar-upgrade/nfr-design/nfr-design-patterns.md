# F6 console-sidebar-upgrade · NFR Design Patterns

## P1 — 단일 소스 반응형 폭 (FR-1) — critic #7
- 폭은 **하나의 시그널**(콘솔 context, `sidebarVisible`과 **독립**)로만 보유. `Sidebar`의 `width`·`index.tsx contentWidth`·
  F5 가시성 토글이 모두 동일 시그널 구독 → 분기 불가(레이아웃 일관, F5 머지 계약). 초기값 `loadWidth()`.
- 드래그: 핸들 box(**`selectable={false}`**, critic #2)가 `onMouseDrag(e)` → `setWidth(clamp(dims.width − e.x, 24, dims.width − MIN_CONTENT))`.
  터미널 리사이즈 시 `dims` 변경 → 재클램프(파생). 캡처는 첫-drag hit-target → 핸들 시작 필요(R1 스파이크).

## P2 — 디바운스 + 원자적 영속 (FR-1.1)
- `onMouseDragEnd`에서만 저장(드래그 중 I/O 없음), 250ms 디바운스. 쓰기 = temp 파일 + `rename`(부분쓰기 방지).
- `loadWidth()` 우선순위 saved > env > 42; 모든 실패는 다음 단계로 폴백(예외 비전파, BR-4).

## P3 — snapshot 확장 (FR-2/3, NFR-2) — critic #1/#4/#5
- **account**: `publish_snapshot._build()`(워커)에서 기존 `ps` + **`equity_log.snapshot(ps)` 재사용**(critic #5) →
  페이로드 `account` 가산. broker 추가 호출 0.
- **round_trip**: **별도 저빈도(30~60초) 잡**에서 `broker.get_fills(since=et_midnight)`(F3 정렬 포트, 저빈도 호출 1종)
  → `summarize_today_round_trips(fills, now_et=...)`(`match_round_trips` + UTC→ET zoneinfo, critic #4). 페이로드 `round_trip` 가산.
  파일(`trades.jsonl`)은 eod 전용이라 사용 금지(critic #1).
- broker 접근 스레드는 **워커 단일** 유지(NFR-2). fills 잡도 워커 경유(`bus.submit`)로 직렬화 → 동시성표 참조. 콘솔은 broker 미접근.

## P4 — monitor 발행: 저빈도 잡 + 원자적 read 파일 (FR-4)
- 신규 `publish_monitor()` = `scheduler.add_seconds_job`로 등록(예: 5초). turns/decisions/log **요약만** 생성
  (tail N + 오늘 누적) → `steering/monitor.json`(또는 뷰별 파일) **원자적 쓰기**.
- 소비: `steer_read{view}`가 해당 파일 읽어 반환. torn-safe 읽기(기존 패턴). 부재/빈 → graceful 메시지.
- **read-only + contract 경계**: 콘솔은 `STEERING_DIR` 밖(workspace/logs) 직접 접근 안 함(BR-11).

## P5 — fail-closed 표시 (NFR-5/BR-8/BR-15)
- 발행 빌드 실패 → 기존처럼 skip+warn. 사이드바는 신규 필드 부재 시 블록 숨김(구/신 호환). 콘솔 비충돌.

## P6 — 보안 (SECURITY-03/11/15)
- log tail 발행 시 토큰/시크릿 패턴 라인 마스킹/제외(SECURITY-03). 신규 경로 모두 read-only, 권한분리 불변(SECURITY-11).
- 파일 I/O·발행 예외는 fail-closed(SECURITY-15).

## 동시성 표
| 스레드/주체 | broker | trades.jsonl/turns/decisions/log | steering/ 쓰기 | ui.json |
|---|---|---|---|---|
| 데몬 워커(publish_snapshot) | read(기존 ps) | read(trades) | snapshot 원자적 | — |
| 데몬 잡(publish_monitor) | — | read(요약) | monitor 원자적 | — |
| 콘솔(렌더/드래그) | — | — | — | read/원자적 write |
| MCP steer_read | — | — | read | — |
→ broker 접근은 데몬 워커 단일(NFR-2). 콘솔은 read-view/ui.json만. 교차 쓰기 경합 없음.
