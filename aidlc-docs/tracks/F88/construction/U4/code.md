# F88 / U4 — TriggerEvaluator & lifecycle & wake 통합 construction record

## 설계 (critic 반영 전부 코드화)
- `TriggerEvaluator.tick()` (스케줄러 진입, best-effort never-raise): run_state 게이팅 → due 트리거만
  build_ctx → sandbox.run → state 갱신 → fire 버퍼 → `reconcile_worker.trigger(self._fire,
  kind="agent_trigger", timeout=wake_timeout)`. `_fire`가 fire 시점에 버퍼 drain → wake_runner(events).
- **critic#3 게이팅(안전)**: run_state_fn 주입, `paused`→전부 억제(평가 전 short-circuit),
  `entries_halted`→entry_inducing 트리거 wake 억제(평가는 함). run_state_fn 예외→억제(fail-safe).
- **critic#4 레인/coalesce**: 별 kind `"agent_trigger"` 레인(wake 레인 미클로버). 한 tick 다수 fire→
  버퍼에 모아 한 wake turn. (레인 경쟁/timeout은 ReconcileWorker가 처리.)
- **critic#6 macro wake**: `prompts.macro_triggers_from_events()` + `wake_prompt(macro_triggers=)`
  분기 추가, `orchestrator.run_wake`가 payload thesis 추출→주입. macro면 심볼-only 제약 해제,
  포트폴리오 재평가 허용.
- **fail-closed/lifecycle**: sandbox error→consecutive_errors++; ≥max→disabled. 성공→카운터 리셋.
  rate-limit `min_fire_gap_s`(기본 6h)로 지속-true 트리거의 wake 폭주 방지. due: last_run+cadence
  interval(hourly 3600/daily 86400, slack 30s).

## 검증
- `tests/triggers/test_evaluator.py` (fakes) + `test_wake_macro.py` → **15 passed**.
  fire emit·no-fire·paused 억제·entries_halted 억제(entry_inducing)/허용(protective)·run_state 실패 억제·
  연속에러 auto-disable·에러후 성공 리셋·rate-limit·not-due skip·coalesce.
- **회귀**: `tests/intraday` 110 passed, `tests/triggers` 전체 91 passed — run_wake/wake_prompt 변경
  기존 wake 안 깨뜨림.

## Security 컴플라이언스 (U4)
SECURITY-11(rate-limit·오용 억제·plane 분리 유지), 15(fail-closed·tick 예외 격리), gate 불변(FR-8).
**핵심 안전**: entries_halted 우회 불가(critic#3) — 테스트로 실증.

## 파일
- 신규: `src/agent/triggers/evaluator.py`, `tests/triggers/{test_evaluator,test_wake_macro}.py`
- 수정: `src/agent/prompts.py`(wake_prompt macro 분기 + 헬퍼), `src/agent/orchestrator.py`(run_wake 주입)
