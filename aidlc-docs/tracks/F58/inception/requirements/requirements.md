# F58 요구사항 — 과거 구간 상단바 비용 표시

## 문제
타임라인을 과거 날짜/구간(`[<]`)으로 이동하면 상단바(NavRow)에 턴들의 사용량(비용)
지표가 사라진다. 현재 `· $cost` 는 `isLive()` 일 때만 `today_cost_usd`(해당 ET세션 전체)로
표시되고, 과거 윈도우에서는 아무것도 안 보인다.

## 사용자 결정 (2026-06-04 클arifying)
- **표시 지표**: 기존 비용 `· $X.XX` 지표를 과거 윈도우에도 표시. (토큰 수 별도 표기 X →
  Python 데몬/타입 변경 불필요, TS-only.)
- **집계 범위**: 현재 보이는 **타임라인 윈도우** `[viewStart, viewEnd)` 내 턴들의 `cost_usd`
  합산. 라이브/과거 동일 규칙 적용 → `isLive` 특수처리 제거(단순화).

## 기능 요구사항
- FR-1: NavRow 는 라이브/과거 구분 없이 항상 `· $<합계>` 를 표시한다.
- FR-2: 합계 = 현재 뷰 윈도우 `[viewStart, viewEnd)` 에 `ts` 가 속하는 `session().turns` 의
  `cost_usd` 합. 파싱 불가 `ts` 는 제외(0 취급).
- FR-3: 윈도우를 `[<]`/`[>]`/`[Live]` 로 옮기면 합계가 그 윈도우 기준으로 재계산된다.
- FR-4: 윈도우에 턴이 없으면 `· $0.00` 표시(빈 구간임을 명시; 기존 라이브 always-show 일관).

## 비기능 / 범위
- 단일 파일 변경: `operator-console/cli/packages/tui-trading/src/components/timeline-bar.tsx`.
- 데이터: `session().turns[*].cost_usd` (과거=turns.jsonl, 라이브=monitor.json — 둘 다 보유).
- 동작 변경 주의: 라이브 바가 기존 `today_cost_usd`(ET세션 전체) → **윈도우 합계**로 바뀜
  (사용자가 윈도우 범위 선택). 라이브 12h 윈도우는 보통 당일 대부분 턴을 포함.

## 검증
- 윈도우 합산 로직을 작은 순수 함수로 분리해 단위테스트(윈도우 경계 in/out, 멀티날짜,
  파싱불가 ts, 빈 윈도우).
- `timeline-bar.tsx` typecheck clean.
- (선택) 라이브 육안: 과거로 이동 시 `· $` 가 그 구간 합으로 표시·갱신.
