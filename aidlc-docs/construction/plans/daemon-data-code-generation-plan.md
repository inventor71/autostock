# Code Generation Plan — Unit A: daemon-data (Python)

## 유닛 컨텍스트
daemon이 TUI에 보낼 데이터를 확장. 턴 ID 생성, Decision 모델 확장, monitor.json 구조화,
진행 중 턴 표시(current_turn). 수정 파일 5개, 0 new runtime deps.

## 데이터 계약 (Unit B가 소비)
`steering/monitor.json` 스키마:
```json
{
  "ts": "2026-06-01T10:30:00",
  "current_turn": {"id": "I3", "type": "intraday", "started_at": "10:31"} | null,
  "turns": {
    "today_count": 5,
    "today_cost_usd": 2.34,
    "recent": [
      {"id": "R1", "type": "research", "ts": "09:30", "cost_usd": 1.20,
       "num_decisions": 3, "duration_ms": 45000, "summary": "Research: BUY AAPL(0.8), BUY MSFT(0.6), HOLD GOOGL(0.5)",
       "health": "ok"},
      ...
    ]
  },
  "decisions": [
    {"turn_id": "R1", "ts": "09:31", "symbol": "AAPL", "action": "BUY",
     "confidence": 0.8, "reason": "Strong momentum...", "source": "agent"},
    ...
  ],
  "log": ["..."]
}
```

## 워크트리 게이트
Part 2 첫 액션으로 `scripts/worktree-setup.sh F22 --py` 실행.
서브모듈은 Unit A에서 건드리지 않음 (Unit B에서 처리).

---

## Step 0: 워크트리 생성
- [x] `scripts/worktree-setup.sh F22 --py` 실행 (또는 수동 `git worktree add`)
- [x] `.env` 심링크 확인
- [x] 레지스트리 행 업데이트 (base commit, branch, worktree 경로)

## Step 1: turn_log.py — turn_id 생성 + summary 빌더
- [x] `generate_turn_id(path, turn_type) -> str` 추가
  - 타입 접두사 매핑: `{"research": "R", "intraday": "I", "wake": "W", "eod": "E", "reconcile": "C"}`
  - 오늘 해당 타입의 기존 turn_id에서 최대 번호 추출 + 1
  - 반환: `"{prefix}{number}"`
- [x] `build_turn_summary(turn_type, decisions) -> str` 추가
  - 결정 기반 자동 조합 (최대 4개, 초과 시 `+N more`)
  - 결정 없으면 `"{Type}: no decisions"`
- [x] `record_turn()` 시그니처 확장:
  - 새 파라미터: `turn_id: str`, `summary: str = ""`, `error: bool = False`
  - 레코드에 `turn_id`, `summary`, `health` 필드 추가
  - `health`: `"error"` if error else `"ok"`
- [x] 테스트: `tests/test_turn_log.py` (신규)
  - `generate_turn_id` 순차 증가, 타입별 독립, 빈 파일 시 1부터
  - `build_turn_summary` 결정 있음/없음/4개 초과
  - `record_turn` 확장 필드 포함 확인

## Step 2: journal.py — Decision 모델 확장
- [x] `Decision`에 `turn_id: str | None = None` 필드 추가
  - pydantic Optional, 기본값 None (하위호환)
- [x] 기존 테스트 무변경 확인 (Optional이므로 기존 Decision 파싱 깨지지 않음)

## Step 3: orchestrator.py — turn_id 전파
- [x] `_run()` 메서드 수정:
  - 턴 시작 시 `generate_turn_id()` 호출로 ID 확보
  - decisions 읽은 후 각 `decision.turn_id = turn_id` 설정
  - `record_turn()`에 `turn_id=turn_id`, `summary=build_turn_summary(...)` 전달
- [x] `_run()`에서 예외 시에도 turn_id 일관성 유지 (예외 시 record_turn with error=True)
- [x] 테스트: 기존 오케스트레이터 테스트에 turn_id 전파 검증 추가 (또는 새 테스트)

## Step 4: runtime.py — monitor.json 구조화
- [x] `_turns_summary()` 수정: 문자열 → MonitorTurnEntry dict 배열
  - `id`, `type`, `ts`(HH:MM), `cost_usd`, `num_decisions`, `duration_ms`, `summary`, `health`
- [x] `_decisions_tail()` 수정: 문자열 → MonitorDecisionEntry dict 배열
  - `turn_id`, `ts`(HH:MM), `symbol`, `action`, `confidence`, `reason`(60자), `source`
- [x] `SteeringRuntime`에 `_current_turn: dict | None` 인스턴스 변수 추가
- [x] `set_current_turn(turn_id, turn_type)` / `clear_current_turn()` 메서드 추가
- [x] `publish_monitor()`에 `"current_turn"` 필드 추가
- [x] 테스트: `tests/test_steering_monitor.py` (신규 또는 기존 확장)
  - _turns_summary 구조화 출력 검증
  - _decisions_tail 구조화 출력 검증
  - current_turn set/clear 동작

## Step 5: modes/agent.py — current_turn 연동
- [x] 턴 실행 래퍼에서 `steering.runtime.set_current_turn()` / `clear_current_turn()` 호출
  - `_scheduled_turn()` 또는 각 `_premarket_research`/`_intraday`/`_eod` 에서
  - try/finally로 보호 (SECURITY-15: fail-safe)
- [x] steering이 None일 때 (비활성) no-op 확인

## Step 6: 회귀 테스트 + 통합 확인
- [x] 전체 기존 테스트 스위트 통과 (0 regressions)
- [x] 새 테스트 통과
- [x] import smoke: `python -c "from src.agent.turn_log import generate_turn_id, build_turn_summary"`
- [x] PBT: `generate_turn_id` 순차 속성, `build_turn_summary` 결정론 속성 (Hypothesis)

## Security Baseline 준수
- **SECURITY-03**: turn_id/summary에 토큰/API키 포함 불가 (결정론적 생성, 구조적 안전)
- **SECURITY-11**: 턴 ID 생성은 turn_log 모듈에 격리; Decision 확장은 하위호환
- **SECURITY-15**: current_turn의 try/finally fail-safe; error health 기록

## 예상 변경량
- 수정: 5 파일 (turn_log.py, journal.py, orchestrator.py, runtime.py, modes/agent.py)
- 신규 테스트: ~15-20개 (turn_id 생성, summary 빌더, monitor 구조화, current_turn, PBT)
- 0 new runtime deps
