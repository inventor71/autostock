# Functional Design — 비즈니스 규칙 (Intraday 루프 재설계 F3)

> 기술-비종속. **불변식·정책·경계**를 BR 번호로 명세. 엔티티=domain-entities.md, 흐름=business-logic-model.md.
> 결정: Q1=A, Q2=A,B, Q3=A, Q4=A(i), Q5=A, Q6=A, Q7=B, Q8=B.

---

## BR-1 — Advisor-only (최우선 불변)
- F3가 추가하는 어떤 컴포넌트(BriefAssembler/WakeDetector/WatchEvaluator/뉴스 폴러/watch 도구)도 **주문을 발행하지 않는다**.
- 주문은 `decisions.jsonl` → `gate_agent_decision` → RiskManager → Broker 단일 경로로만. F3는 이 경로를 **읽지도 수정하지도 않는다**(BLM-8).
- watch 도구(`watch set/clear`)는 감시 조건만 기록 — stop/target을 자동 적용하지 않는다(FR-5: 조건 충족 → LLM이 판단·결정).

## BR-2 — Turn 직렬화 (NFR-1)
- 모든 intraday LLM 발화(스케줄 + wake)는 main `TurnCoordinator` turn_lock 경유. **bare `session.run_turn` 금지**(두 `claude --resume` 동시 실행 금지).
- 스케줄 turn = `try_scheduled_turn`(non-blocking, 점유 시 스킵). wake turn = `reconcile_turn`(우선·bounded-blocking) 봉투, `ReconcileWorker.trigger(kind="wake")` 경유.
- 새 동시성 프리미티브 생성 금지 — main 것을 일반화·확장만(C-1/C-4 기이행 재사용).

## BR-3 — 우선순위 & skip-if-busy (FR-3, C-2)
- **wake turn > 스케줄 turn**: reconcile waiting 또는 turn in-flight면 스케줄 발화는 **스킵(큐잉 아님)**.
- back-to-back(직전 turn이 슬롯 직전 종료)은 허용.
- "skip"(실행 중 turn 있음)과 "yield"(대기 중 reconcile에 양보)는 구분(main `try_scheduled_turn`이 이미 둘 다 처리: `busy` vs `reconcile_waiting`).
- **검증**: "15분 슬롯에 wake turn 실행 중 → 스케줄 스킵(큐잉 아님)" 통합테스트(§NFR-6).

## BR-4 — Wake 조건 한정 (FR-4, 잠긴 아키텍처 §4)
- wake는 **판단이 필요한** 이벤트만: `new_fill` / `abnormal_move` / `watch_trigger` / `protective_reassess`.
- **단순 "가격이 레벨에 닿음"은 wake 아님** — 거래소 resting OCO가 기계적 트리거(LLM은 "닿았나" 부담 안 짐).
- **뉴스는 wake 아님**(FR-6 — 스케줄 brief가 읽음). **EOD 강제는 wake 아님**(기존 EOD turn).
- wake turn과 그 뒤 스케줄 turn은 **같은 day session id 공유**(wake 추론이 다음 스케줄에 보임 — 의도된 동작, C-8).

## BR-5 — Brief 규율 (FR-2)
- **BR-5.1 입력 분리(C-7)**: 시장데이터(가격/거래량/지표)는 데몬 `data_provider` 직접. account/체결은 `SteeringState.snapshot()` 캐시만 — **brief 조립 중 broker 직접 호출 금지**(NFR-2, 단일워커 불변식).
- **BR-5.2 체결 진실(Q3=A)**: 체결은 broker fills 커서(snapshot 경유)로만 — 시세 추론(가격이 레벨 터치)으로 체결을 판단하지 않는다(현행 META 버그 금지).
- **BR-5.3 human-context 포함(신규, critic#1)**: 매 intraday/wake turn brief는 사람 컨텍스트(활성 directive·대기 승인·종목 락)를 담는다. **`_with_human_context`라는 prepend는 존재하지 않으며**(F4는 `_recent_context`를 `run_reconcile`에만 주입, `runtime.py:75`), 스케줄/wake turn은 현재 사람 컨텍스트 0 → **F3가 직접 담는 신규 작업**(유지 아님). 미포함 시 사람이 방금 락한 종목 재진입 위험.
- **BR-5.4 렌더(Q6=A)**: 컴팩트 구조화 텍스트(종목별 1~2줄, 레벨 거리%). JSON 아님. **`review.outcome_lines` 재사용은 *문자열 포맷 형태*에 한함** — 그 함수는 `broker.get_position`을 직접 호출(`review.py:42`)하므로 호출/데이터-조립 재사용 금지(BR-5.1·NFR-2 위반, critic#6). 데이터는 snapshot+data_provider에서.

## BR-6 — watch.jsonl 규율 (FR-1/FR-5, Q1=A, Q2=A,B, C-5)
- **BR-6.1 단일 writer**: `workspace/watch.jsonl`은 agent 도구 `watch set/clear`만 append — agent가 파일을 직접 쓰지 않음(advisor-only 경계).
- **BR-6.2 어휘 한정(Q2)**: v1 조건은 `price_above`/`price_below`/`close_above`/`close_below` 4종. 그 외 거부(fail-closed, SECURITY-15). `close_*`는 마감 확정 바에서만 평가.
- **BR-6.3 torn-line/읽기커서(C-5)**: `jsonl.read_complete_lines` + `ByteCursor` 재사용은 **watch.jsonl 읽기 위치**에만 — 미완성 trailing line skip, 완전 라인만 커서 진행.
- **BR-6.4 fired 1회/일(critic#5)**: 발화 여부는 ByteCursor가 아니라 **별도 영속 구조 `{et_date, fired_ids:set[str]}`**로 추적(정수 오프셋은 날짜 스코프·id-set 표현 불가). 발화 시 id 추가 → 재시작·재평가 후 재발화 금지. 동일 트리거 하루 1회.
- **BR-6.5 만료/리셋**: `valid_until` 경과는 ET 자정 `daily_sweep`(main `sweep_expired` 합류)이 expired 처리하고, **같은 sweep가 `et_date` 전환 시 `fired_ids` 초기화**. 읽기 ByteCursor는 0으로 되돌리지 않음(append-only 단조).

## BR-7 — new-fill 감지 (FR-4-A, Q3=A, C-3, critic#3)
- 감지 입력 = **broker 활동내역(activities) 이벤트**. 신규 `get_fills(since)` 포트는 **`GetActivitiesRequest(activity_types=[FILL])`** 기반(건별 체결 이벤트+안정 id). 기존 `_alpaca_fills`(주문단위 `get_orders`, `trades_log.py:45`)는 부분체결·동일수량 교차를 못 잡으므로 **재사용 아님 — 신규 broker 작업**.
- positions qty diff 추론·시세 터치 추론 금지(현행 META 버그 차단).
- 접근 = bus job → snapshot 페이로드 체결-이벤트 확장(NFR-2). 감지기는 snapshot만 읽음.
- activities `since` 커서 단조 전진 + activity `id` idempotent(같은 체결 재wake 금지; 이벤트 id 기반이라 부분체결 미합산).

## BR-8 — abnormal-move (FR-4-C, Q4=A(i), critic#7)
- 판정: 일중 `|가격이동| > k×ATR(14)` **또는** `vol > m×평균`(기본 k=1.5, m=3). 둘 중 하나.
- 설정: `config/settings.yaml`의 `intraday.abnormal_move`(atr_k/vol_multiple/atr_period). 블록 부재 시 기본값 fail-safe.
- **입력 fetch ≠ 판정 계산 분리(critic#7)**: ATR(14)는 종목별 14+ intraday 바 필요. `data_provider.get_bars`는 **캐시 없음**(yfinance intraday는 레이트리밋/coarse, `yfinance_provider.py:86-89`) → 5초 감지 틱마다 전체 재fetch 금지. **바 입력은 1~5분 주기 캐시(best-effort)**, 그 위에서 ATR/평균/임계 비교만 **순수 함수**(PBT 대상, BR-13).

## BR-9 — coalesce (FR-4, Q5=A, C-4, critic#2)
- debounce 창 안 다수 WakeEvent → **하나의 wake turn**(사유 다중 프롬프트).
- **버퍼 소유권**: typed-event 버퍼는 **WakeDetector가 소유**하고 **발화 시점(run_fn 안)에 drain**한다. `ReconcileWorker._pending[kind]`는 kind별 **최신 run_fn 1개만** 유지(`turns.py:98`)하므로 이벤트를 거기 넣으면 trigger 사이 이벤트 유실 — dict에 넣지 않는다.
- **human 굶김 방지**: main ReconcileWorker는 debounce 타이머가 **kind 공유**(`turns.py:99-101`)·`_fire` 순차(`:110`)라, 잦은 wake가 `human` reconcile을 무한 지연·차단한다. → **wake 레인과 human 레인 타이머 분리(또는 kind별 타이머) + wake `reconcile_turn` 타임아웃 단축**(기본 600s, `turns.py:53`). 이는 ReconcileWorker *수정*(C-1처럼 순수 재사용 아님).
- 같은 종류 연속 트리거는 debounce로 흡수(중복 turn 방지).

## BR-10 — 뉴스 diff (FR-6, Q8=B, C-6)
- 범위 = 보유 + watch 종목. 주기 TTL ≥ 15분. per-symbol `last_seen_key` 영속(중복 제거).
- **wake 트리거 아님** — 스케줄 turn brief에만. wake turn brief에는 미포함.
- best-effort(레이트리밋/예외가 데몬·brief 비중단).

## BR-11 — RunState 게이팅 (FR-7, **Q7=A** [critic#4로 B→A 전환], C-8)
- **paused**: 모든 wake 발화 보류 + 보류 사실 최소 로그(감지기 책임 — orchestrator 호출 전 early-return 아님). 정상 운영엔 heartbeat 없음(C-1).
- **entries_halted (Q7=A)**: WakeDetector가 **`entry_inducing=True` WakeEvent를 발화하지 않는다**(detector-레벨 억제). **B(프롬프트+gate 차단)를 버린 이유**: `gate_agent_decision`은 entries_halted를 **안 본다**(`gate.py:8` 명시 — 사람 락만) → "gate 최종 차단" 안전망이 실재하지 않음. 그래서 발화 자체를 억제.
- `entries_halted`는 main 무소비자(`state.py:146` set만 존재) → **소비 훅 신규** = WakeDetector가 `RunState.entries_halted` 읽어 `entry_inducing` wake 드롭.
- `entry_inducing` 분류(상승 abnormal-move + 진입성 watch=True; new_fill·protective·SELL=False)는 순수함수(PBT). 오분류 시 **억제 쪽(True)으로 보수 처리**(fail-closed).
- 보호선/ADJUST_STOP/SELL/new_fill wake는 entries_halted와 무관하게 항상 정상 발화.

## BR-12 — Fault isolation (NFR-4)
- wake 감지·brief 조립·뉴스 폴링·watch 평가의 **예외는 로깅 후 계속** — 데몬을 죽이지 않는다(F4 best-effort 패턴).
- brief 섹션 일부 실패 시 그 줄만 비우고 turn 진행(brief 조립 실패가 turn 자체를 막지 않음).

## BR-13 — 보안/테스트 (NFR-5)
- **SECURITY-03**: brief·로그·watch 기록에 비밀(키/토큰) 미포함.
- **SECURITY-15 fail-closed**: 알 수 없는 watch 조건·결손 입력은 거부/보수적 처리(임의 진행 금지).
- **PBT 대상(Hypothesis, Partial)**: (a) abnormal-move 판정 순수함수(임계 경계 단조), (b) 레벨 거리(%) 계산, (c) watch 조건 평가(`price_*`/`close_*` 경계), (d) activities/fired-set 단조성·idempotency(중복·역행 없음), (e) `entry_inducing` 분류(fail-closed 보수성).

## BR-14 — 변경하지 않는 경계 (재확인)
- 결정/주문 경로 불변(BLM-8). agentic path backtest 비대상(검증=paper/live + 단위/PBT). snapshot/JSONL/turn **골격**은 main(F4) 것 그대로.
- ⚠ 단, **ReconcileWorker는 수정 대상**(BR-9, critic#2: kind별/레인 분리 타이머)·**broker 포트는 확장 대상**(BR-7, critic#3: `get_fills` activities)·**snapshot 페이로드 확장**(BLM-6) — "순수 재사용"이 아닌 부분을 명시. 새 동시성 *프리미티브*(lock/coordinator 자체)는 만들지 않음.

---

## 추적성 (BR ↔ FR ↔ Q ↔ critic)
| BR | FR | Q | §11 critic | 2차 /critic(2026-05-30) |
|---|---|---|---|---|
| BR-1 | §4 advisor-only | — | — | — |
| BR-2/3 | FR-3, NFR-1 | C-2 | C-1(기이행) | — |
| BR-4 | FR-4 | Q2 | — | — |
| BR-5 | FR-2 | Q3,Q6 | C-3, C-7 | **#1**(human-context 신규), **#6**(outcome_lines 포맷만) |
| BR-6 | FR-1/5 | Q1,Q2 | C-5 | **#5**(fired-set ≠ ByteCursor) |
| BR-7 | FR-4-A | Q3 | C-3 | **#3**(activities API 신규) |
| BR-8 | FR-4-C | Q4 | — | **#7**(바 캐시/계산 분리) |
| BR-9 | FR-4 | Q5 | C-4 | **#2**(타이머 분리·버퍼 소유·human 굶김) |
| BR-10 | FR-6 | Q8 | C-6 | (뉴스 폴링 스레드 필수) |
| BR-11 | FR-7 | **Q7=A** | C-8 | **#4**(gate 무차단→detector 억제로 B→A) |
| BR-12 | NFR-4 | — | — | — |
| BR-13 | NFR-5 | Q12 | — | — |
| BLM-1/3 | FR-2/3 | — | — | **#8**(run_intraday 무인자 → 빌더+시그니처+호출부 배선) |

> **2차 /critic 검토(2026-05-30, 격리 서브에이전트)**: 8건(HIGH 3 / MED 4 / LOW 2) 전부 `path:line`으로 코드 교차검증 → 유효. 정책 분기 2건은 사용자 결정으로 해결: **#4 → Q7=A**(entries_halted = detector 억제, gate는 무차단이 사실), **#3 → activities API 채택**(`GetActivitiesRequest(FILL)` 신규 broker 작업). 나머지 6건은 엔지니어링 보강으로 위 BR/BLM에 반영.
