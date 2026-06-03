# Decision Quality Metrics — Code Generation Plan

## 개요
단일 unit `decision-quality-metrics`. 신규 `src/agent/quality/` 모듈 + CLI 진입점 +
executor에 execution_log.jsonl append + EOD 프롬프트 연동.

**신규 런타임 의존성**: 0
**위험도**: Low (읽기 전용 분석 + execution_log append 1개소)

## Step 0: Worktree 생성
- [x] `git worktree add .claude/worktrees/F24 -b feat/F24 main`
- [x] 이후 모든 코드 작업은 worktree 내에서

## Step 1: execution_log.jsonl 영속화 (FR-1.5 전제)
- [x] `src/agent/executor.py`에 `_log_execution()` 메서드 추가
  - `execute_decision()` 성공 시 `workspace/execution_log.jsonl`에 append:
    `{decision_index, symbol, action, order_id, filled_qty, filled_price, ts}`
  - `Journal` 인스턴스의 root 기준 경로
  - atomic append (기존 `decisions.jsonl` 패턴 따라감)
- [x] `ExecutionOutcome`에서 `filled_qty`, `filled_price` 추출 (broker `submit_order` 반환값)
- [x] 테스트: execution_log append + 파싱 round-trip

## Step 2: DecisionOutcome 데이터 모델 + 수집기 (FR-1)
- [x] `src/agent/quality/__init__.py` — 패키지 생성
- [x] `src/agent/quality/models.py` — `DecisionOutcome` Pydantic 모델:
  - decision: Decision
  - execution: {order_id, filled_qty, filled_price, filled_at} | None
  - round_trip: {entry_price, exit_price, opened_at, closed_at, realized_pnl} | None
  - price_path: list[{date, open, high, low, close}] (보유기간 일봉)
  - match_method: "execution_log" | "heuristic"
- [x] `src/agent/quality/collector.py` — `collect_outcomes()`:
  1. `Journal.read_decisions()` — BUY/SELL만 필터 (HOLD/ADJUST_STOP 제외)
  2. `execution_log.jsonl` 파싱 → decision_index로 매칭; 없으면 symbol+time 휴리스틱
  3. `get_fills()` → FillEvent→dict 변환 → `match_round_trips()`
  4. yfinance 일봉 배치 fetch (심볼별 1회, 캐시)
  5. round-trip + price_path 조인 → `list[DecisionOutcome]`
- [x] 테스트: collector mock 데이터 round-trip

## Step 3: 메트릭 계산 엔진 (FR-2)
- [x] `src/agent/quality/metrics.py` — 순수 함수 (DataFrame/list 입력, dict 출력):
  - `direction_hit_rate(outcomes) -> {total, hits, rate}` — BUY만
  - `mae(outcome) -> float` — (entry - min(low)) / entry
  - `mfe(outcome) -> float` — (max(high) - entry) / entry
  - `stop_quality(outcome) -> "appropriate" | "noise_hit" | "held" | "n/a"`
  - `target_quality(outcome) -> {reached: bool, days_to_reach: int | None}`
  - `confidence_calibration(outcomes) -> dict[str, {count, hits, rate}]` — unscored 제외
  - `realized_rr(outcome) -> float | None`
  - `benchmark_excess(outcome, spy_path, qqq_path) -> {vs_spy, vs_qqq}`
  - `exit_timing(outcome) -> float` — SELL 후 N일 기회비용
- [x] 테스트: 각 함수 example + Hypothesis PBT (mae/mfe 범위 invariant, calibration 합계)

## Step 4: 집계 + 롤링 (FR-3)
- [x] `src/agent/quality/aggregate.py`:
  - `summary(outcomes) -> dict` — 전체 기간 평균/중앙값/분포
  - `rolling(outcomes, window=20) -> list[dict]` — 최근 N건씩 롤링
- [x] 테스트: 빈 입력, 단일 입력, 정상 입력

## Step 5: CLI 리포트 (FR-4)
- [x] `src/agent/quality/__main__.py`:
  - `report` 커맨드 (기본): collect → metrics → aggregate → Rich 테이블 출력 + JSON 저장
  - JSON 저장 경로: `workspace/quality/<date>.json`
  - 브로커/데이터 프로바이더는 main.py와 동일 설정 로드
- [x] 테스트: CLI smoke (mock 데이터)

## Step 6: EOD 프롬프트 연동 (FR-5)
- [x] `src/agent/quality/snapshot.py`:
  - `quality_snapshot(outcomes) -> str | None` — 요약 텍스트 (< 5건이면 None)
- [x] `src/agent/prompts.py` — `eod_review_prompt(outcomes, quality_summary=None)` 파라미터 추가
  - None이 아닐 때만 "## Decision Quality Metrics" 섹션 주입
- [x] `src/agent/orchestrator.py` — `run_eod_review()` 호출 시 quality_summary 전달
- [x] `src/trading/modes/agent.py` — `_eod()`에서 quality 모듈 호출 + 전달
- [x] 테스트: 프롬프트에 포함/미포함 케이스

## Step 7: 테스트 + 회귀
- [x] 전체 테스트 스위트 실행 — 기존 테스트 0 regression
- [x] F24 신규 테스트 목록 정리
- [x] Hypothesis PBT: metrics 순수 함수 invariant (PBT-02/03)
- [x] SECURITY-03 확인: 로그에 API key/account 정보 노출 없음
- [x] SECURITY-15 확인: 데이터 부족 시 빈 리포트 (에러 아님)

## Step 8: DESIGN.md + README 갱신
- [x] DESIGN.md §5.8에 Quality Metrics 하위 섹션 추가
- [x] README features 테이블에 "Decision Quality Metrics" 추가

## 파일 변경 요약

### 신규 파일
- `src/agent/quality/__init__.py`
- `src/agent/quality/__main__.py`
- `src/agent/quality/models.py`
- `src/agent/quality/collector.py`
- `src/agent/quality/metrics.py`
- `src/agent/quality/aggregate.py`
- `src/agent/quality/snapshot.py`
- `tests/test_quality.py` (또는 `tests/test_quality/` 하위 분할)

### 수정 파일
- `src/agent/executor.py` — `_log_execution()` 추가 (1 메서드)
- `src/agent/prompts.py` — `eod_review_prompt()` 파라미터 추가
- `src/agent/orchestrator.py` — quality_summary 전달
- `src/trading/modes/agent.py` — quality 모듈 호출
- `DESIGN.md` — §5.8 하위 섹션
- `README.md` — features 테이블
