# Code Generation 계획 (Part 1) — Intraday 루프 재설계 (F3)

> Unit `intraday-redesign`. **신규 런타임 deps 0.** 베이스 = `main` 분기 worktree+branch.
> 승인 시 Part 2의 **첫 동작 = worktree 생성**(Q10/Q11=A), 이후 Step 1~11을 거기서 구현. 현재 코드/worktree 없음.
> 각 Step = 구현 + 테스트 + 그 Step 그린 후 다음. 설계 근거: functional-design/* + nfr-design/*.

## Step 0 — worktree (Part 2 첫 동작) ✅
- [x] `git worktree add .claude/worktrees/intraday-redesign -b feat/intraday-redesign main` (e231015)
- [x] 베이스 테스트 그린 확인(282 passed).

## Step 1 — F3 레코드 ✅ (826335a)
- [x] `src/agent/intraday/records.py`: `WatchTrigger`/`WatchRecord`/`WakeEvent`/`FillEvent`/`SnapshotDelta`/`NewsDiff`/`AbnormalMoveSignal`(pydantic). condition v1 4종 Literal.
- [x] `tests/test_intraday_records.py`: 직렬화/검증(잘못된 condition 거부, set은 trigger 필수 — model_validator, fail-closed). 9 passed.

## Step 2 — broker `get_fills` (activities, critic#3 / R1) ✅ (826335a)
- [x] **`src/execution/base.py`**: `get_fills(since)` concrete no-op([]). `alpaca_broker.py`: raw `_client.get("/account/activities", {...})`(`/v2` 없음) → `_to_fill_event` → `FillEvent`(side 필터, ts ISO 파싱, best-effort).
- [x] tests `test_intraday_fills.py`: simulated no-op; AlpacaBroker `_client.get` fake로 파싱·`activity_types=FILL`·`after=since`·activity-id dedup·실패 시 [] (NFR-4). 5 passed. ⚠ R1 라이브(Step 11)가 응답형태 권위.

## Step 3 — snapshot fills 페이로드 + in-proc 캐시 ✅ (e58e7ee)
- [x] `runtime.publish_snapshot`: bus 워커에서 `get_fills(since=cursor)` → 페이로드 `fills` + `.fills.cursor`(atomic) 증분. `_collect_new_fills`.
- [x] **`SteeringRuntime.last_snapshot` in-proc dict** — brief/감지기가 메모리에서 읽음. 첫 실행 cursor="now"(히스토리 미발화).
- [x] tests `test_intraday_snapshot.py`: 신규 체결 1회·커서 영속·idempotent·첫실행 flood 방지. 3 passed.

## Step 4 — watch.jsonl + 도구 + fired-set ✅ (625371e)
- [x] `watch_store.py`: `active()`(read_complete_lines 전체 torn-safe 스캔 — 소파일이라 ByteCursor 불요), `mark_fired/is_fired`(`watch_fired.json{et_date,fired_ids}`), `sweep()`.
- [x] `agent/tools watch set/clear/list`(유일 writer, condition choices 검증, fail-closed).
- [x] tests `test_intraday_watch.py`: active/cleared/expired, malformed skip, fired 하루 1회, ET-date 롤오버 재발화(V4), CLI smoke. 7 passed.

## Step 5 — 바·가격 캐시 + abnormal-move ✅ (625371e)
- [x] `bars.py`: `BarCache`(bars 60s/price 3s TTL, best-effort 캐시 fallback) + 순수 `atr`/`avg_volume`. `abnormal.py`: `detect_abnormal`(ATR k OR vol m) + 순수 predicate `breaches_atr`/`breaches_volume` + `AbnormalConfig`.
- [x] tests `test_intraday_bars.py`: 캐시 TTL 라우팅·실패 시 캐시 반환, price/volume breach, Hypothesis(predicate 단조·strict 경계). 10 passed.

## Step 6 — BriefAssembler (FR-2, critic#1/#6, 2차critic#4/#6)
- [x] `brief.py`: `build(symbols, snapshot, state, news, include_news)` — 시장(data_provider 캐시)+account/fills(**in-proc last_snapshot**)+**human-context(directives/pending/locks)**+델타+뉴스. **held는 snapshot positions에서**(orchestrator.held_symbols=broker 호출 미사용). **별도 포맷터**(outcome_lines 호출 금지), 컴팩트 텍스트(Q6=A). best-effort 섹션.
- [x] tests: human-context 포함, **broker 직접호출 없음**(last_snapshot만, held도 snapshot), **snapshot 비면 account 섹션 생략·조립 성공**(fail-closed), 섹션 결손 시 그 줄 공백.

## Step 7 — 뉴스 diff (FR-6, Q8=B, C-6)
- [x] `news_diff.py`: `NewsPoller`(데몬 스레드, TTL≥15분, 보유+watch 종목), per-symbol `last_seen_key`(`.news_seen.json`) diff, best-effort.
- [x] tests: 신규 헤드라인만 diff, 중복 무시, 폴링 예외 무중단.

## Step 8 — WakeDetector + ReconcileWorker 레인 (FR-4, Q5=A/Q7=A, critic#2/#4, 2차critic#1/#2/#3)
- [x] `turns.py` `ReconcileWorker`: **per-kind 타이머**(무한-취소 굶김만 해소) + **`_fire`가 human-kind 먼저 dispatch**(2차critic#1) + **kind→acquire-timeout을 `reconcile_turn(timeout=)`에 실제 전달**(현재 `:112` 미전달, 2차critic#2). ⚠ 이건 *획득* 타임아웃 — wake LLM 실행 제한은 Step 9의 turn-level `_run(timeout=)`로.
- [x] `wake.py` `WakeDetector.detect_wakes`: **캐시 읽기만**(last_snapshot fills + BarCache/가격캐시, 동기 fetch 금지 2차critic#3)+watch 평가 → `WakeEvent[]`(new_fill/abnormal/watch/protective), 소유 버퍼 적재, `ReconcileWorker.trigger(kind="wake")`. `classify_entry_inducing`(순수, fail-closed). **paused→보류+로그**, **entries_halted→entry_inducing 드롭**(Q7=A).
- [x] tests: V2(wake 폭주가 human 타이머 취소 안 함 + `_fire` human 먼저), **human은 in-flight wake turn 1회분만 대기**(본질적, 단정 아님), V5(halted entry_inducing 억제·그 외 통과), coalesce 1 turn drain, detect_wakes 동기-fetch 없음.

## Step 9 — orchestrator/prompts 배선 (BLM-1/2, critic#8, 2차critic#6)
- [x] `orchestrator.run_intraday(brief)` + `run_wake(brief, events)`(`_run`에 turn_type/prompt + **wake용 `timeout` 전달**=실행 bound); **brief/wake 경로 held는 snapshot에서**(held_symbols=broker 미사용). `prompts.intraday_prompt(brief, held)` + `wake_prompt(brief, events)`(human-context 포함).
- [x] tests: brief가 프롬프트에(공백 가격줄 회귀 방지), wake 프롬프트 사유 다중, wake `_run` timeout 전달.

## Step 10 — 데몬 배선 (BLM-3/7, modes/agent + settings, 2차critic#3/#7)
- [x] `modes/agent._intraday`: BriefAssembler로 brief→`run_intraday(brief)`; `agent_wake` 5초 job 등록(detect_wakes) + seconds-job `misfire_grace_time`(scheduler.py); NewsPoller start/stop; entries_halted 소비.
- [x] **steering=None 폴백**(2차critic#7): brief/wake/news 비활성, 레거시 `intraday_prompt(quotes,held)` 경로 — "이전과 동일"(NFR-8).
- [x] `config/settings.yaml` `intraday:` 블록(abnormal_move/wake/news/bars/price). 주입 경로(U2 패턴, 글로벌 reach-in 금지).
- [x] tests: brief 전달, wake job 등록, paused/halted 경로, **steering=None→레거시 폴백**.

## Step 11 — 통합 + 회귀 + 라이브 검증
- [x] V3 skip-if-busy(wake 실행 중 스케줄 슬롯 스킵), V4 fired 롤오버, 다발 trigger coalesce e2e.
- [x] 전체 회귀 **282 + 신규** 그린. PBT 통과.
- [x] **R1 라이브 — VERIFIED 2026-05-30** (직접, 장 마감 중 read-only `/account/activities`): raw GET가 14개 FILL dict 반환,
      키=id/activity_type/transaction_time/type/side/symbol/qty/price/cum_qty/leaves_qty/order_id/order_status; **id가 `<seq>::<uuid>`로
      partial_fill도 고유**(부분체결 미합산=Q3=A 목표 실증), `after` 커서가 엄격히 신규만 필터, transaction_time RFC3339(Z) ISO 파싱 OK.
      실제 형태를 `test_intraday_fills.py`에 회귀로 고정(072f6ac). 페이지네이션은 단일 GET(≤100/poll, recent `after`로 델타 작음)=알려진 한계.
- [x] DESIGN.md/README 갱신(intraday 재설계 §, watch 도구, settings intraday 블록).

## 완료 기준
- 모든 Step 그린, advisor-only·주문경로 불변(회귀로 보장), 신규 deps 0, agentic backtest 비대상.
- 머지 결정은 Build&Test 후 사용자.

---
### 변경 표면 요약(리뷰용)
- **신규**: `src/agent/intraday/{records,watch_store,bars,abnormal,brief,news_diff,wake}.py`, watch 도구, 6개 workspace 데이터파일, settings `intraday:` 블록, 다수 테스트.
- **수정**: `steering/turns.py`(ReconcileWorker per-kind 타이머+`_fire` human-우선+timeout 전달), `steering/runtime.py`(snapshot fills + `last_snapshot` in-proc), `orchestrator.py`(brief/run_wake/held-from-snapshot/wake timeout), `prompts.py`, `modes/agent.py`(+steering=None 폴백), `trading/scheduler.py`(misfire_grace), `execution/base.py`+`brokers/alpaca_broker.py`(get_fills).
- **불변**: `gate.py`/RiskManager/Broker 주문경로, TurnCoordinator 코어, decisions.jsonl 흐름.
