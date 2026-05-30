# F6 console-sidebar-upgrade · Code Generation Plan (Part 1)

> 0 new runtime deps. 베이스 = `main`에서 worktree+branch. **승인 시 Part 2의 첫 동작 = worktree 생성**; 그 전엔 코드/worktree 없음.
> F5 소유 영역(default-on/리브랜드)은 구현하지 않음(충돌 최소화).

## Step 0 — worktree
- [x] `git worktree add .claude/worktrees/console-sidebar-upgrade -b feat/console-sidebar-upgrade main`.

## Step 1 — Python: account + 라운드트립 발행 (FR-2/3) — critic #1/#4/#5
- [x] **account**: `runtime.publish_snapshot._build()`에서 기존 `ps` + **`equity_log.snapshot(ps)` 재사용**(critic #5) → `account` 가산. broker 추가호출 0.
- [x] **브로커 `get_fills(since)` 포트**(F3 정렬): BaseBroker no-op + Alpaca raw `/account/activities` GET. (F3가 먼저 구현했으면 재사용.)
- [x] `summarize_today_round_trips(fills, *, now_et) -> {closed_count, win_rate, realized_pnl, as_of}` — `match_round_trips` 재사용 + **`filled_at` UTC→ET `zoneinfo` 변환**(critic #4) 후 오늘 필터. 순수.
- [x] **저빈도 잡** `publish_round_trip()`(30~60초): `get_fills` → 집계 → `round_trip` 가산. `add_seconds_job` 등록.
- [x] 테스트: 집계 예시 + Hypothesis(win_rate∈[0,1], count≥0) + **UTC→ET 경계**; `get_fills` no-op/Alpaca 파싱; account=equity_log.snapshot 재사용; round_trip은 fills 경로(trades.jsonl 파일읽기 금지).

## Step 2 — Python: monitor 발행 잡 (FR-4)
- [x] `publish_monitor()` — turns/decisions(torn-safe 읽기) 요약 + log tail(시크릿 마스킹) → `steering/monitor.json` 원자적 쓰기.
- [x] `SteeringRuntime`에 `add_seconds_job(publish_monitor, ~5s)` 등록.
- [x] 테스트: 발행 형식/원자성/부재 graceful; 마스킹.

## Step 3 — TS: `steer_read` view 분기 확장 (FR-4) — critic #3 (4-파일)
- [x] `parser.ts`: read 동사 화이트리스트(line 22)에 `turns`/`decisions` 추가(log/status 기존).
- [x] `filedrop.ts`: `FileDrop`에 `monitor.json`(STEERING_DIR 경계 내) torn-safe 리더 추가.
- [x] `steer-handler.ts`: `handleSteerRead`가 **`draft.verb`로 분기**(status→snapshot, turns/decisions/log→monitor) — 현재 verb 무시·snapshot만 반환 수정.
- [x] `mcp-server.ts`: inputSchema/설명 갱신.
- [x] bun 테스트: verb별 반환·부재 graceful.

## Step 4 — TS: 반응형 폭 + 영속 (FR-1/1.1)
- [x] 폭 상태 모듈(시그널 + `loadWidth`[saved>env>42] + `saveWidth`[디바운스·원자적, XDG ui.json]).
- [x] bun 테스트: `clampWidth` 경계, `loadWidth` 우선순위/폴백.

## Step 5 — TS: 드래그 리사이즈 + 재레이아웃 (FR-1) — critic #2/#7
- [x] 폭 시그널을 `sidebarVisible`과 **독립 context**로 분리(F5 공유 계약, critic #7).
- [x] `sidebar.tsx`: `sidebarWidth()`→시그널 구독; 좌측 DragHandle box **`selectable={false}`** + `onMouseDown/Drag/DragEnd`, `width=dims.width−e.x` 클램프.
- [x] `index.tsx`: 변경 불필요 — 이미 재export된 반응형 `sidebarWidth()`를 `contentWidth` memo에서 구독.
- [ ] tsgo 타입체크 / **R1 라이브 스파이크**(드래그 캡처가 핸들 보유·텍스트 선택 미발생) — **사용자 대기**(서브모듈 deps 미설치로 여기서 빌드 불가).

## Step 6 — TS: 사이드바 계정/성과 + 스타일 (FR-2/3/5)
- [x] `autostock.tsx`: 계정 블록 + 성과 줄 + 섹션 헤더/PnL 색(success/error)/숫자 정렬/빈 상태; 신규 필드 부재 시 숨김(BR-8).
- [ ] tsgo 타입체크 — **사용자 대기**(서브모듈 deps 미설치).

## Step 7 — Build & Test + 재핀 + 라이브
- [x] Python 무회귀(전체 스위트 292) + 신규 테스트 green; bun 테스트 29 green. (tsgo는 서브모듈 deps 미설치로 미실행.)
- [x] 서브모듈 `operator-console/cli` 변경 커밋(82e009b) + 부모 재핀(e696630). (push/merge 안 함.)
- [x] 라이브 R1 — **사용자 확인됨 2026-05-30**(`bun dev` 드래그 리사이즈 동작). [ ] R3(`steer_read` view) / R4(`get_fills` 페이퍼) — **추후 확인 예정.**

## 무회귀/안전 게이트
- 주문/스티어링/권한분리/contract 불변(가산만). F5 충돌 표면 최소(default-on/리브랜드 미구현).
