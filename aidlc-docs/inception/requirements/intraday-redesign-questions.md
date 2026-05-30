# Intraday 루프 재설계 (F3) — 요구사항 명확화 질문

## 의도 분석 (Intent Analysis)
- **요청 유형(Request Type)**: Enhancement (기존 agent intraday 루프 재설계)
- **범위(Scope)**: Multiple Components — `src/agent/prompts.py`(intraday_prompt), `src/agent/orchestrator.py`(run_intraday), `src/trading/modes/agent.py`(_intraday: 게이트/cadence), `src/agent/review.py`(brief 조립 재사용 후보), 신규 결정형 게이트 모듈, journal 스키마(구조화 watch-trigger) 후보
- **복잡도(Complexity)**: Moderate–Complex (라이브 주문 경로에 직접 주문을 넣지는 않으나 — advisor-only 유지 — agent의 의사결정 빈도/입력을 바꾸므로 정합성·비용 영향이 큼)
- **요구사항 깊이(Depth)**: Standard (기능 + 비기능)

## 배경 — 오늘 trace에서 확인된 문제 (요약)
1. 13개 intraday turn 중 결정 산출은 1개뿐, 나머지 12개는 매번 처음부터 5종목 시세를 다시 긁어 같은 표를 재서술 (full LLM 비용).
2. `run_intraday()`가 quotes 없이 호출 → 프롬프트의 가격 줄이 항상 비어 agent가 매 틱 직접 `quote` 호출.
3. intraday에서 `account`/`news`/`scoreboard` 미사용 → META 체결을 **추론**(시세 저가가 $630 터치)으로 판단, broker 진실 미확인 → journal/broker 어긋남 위험.
4. 프롬프트의 "thesis 변화(신규 뉴스/촉매)?" 분기가 사실상 죽어 있음 (intraday에 뉴스를 한 번도 안 봄).

## 잠긴 아키텍처 제약 (이미 결정된 것 — 재설계는 이를 따름)
- **Advisor-only**: agent는 주문을 직접 넣지 않는다. `decisions.jsonl` → RiskManager → Broker가 유일한 주문 게이트.
- **Exchange resting OCO(bracket)**: stop/target은 이미 거래소에 상시 대기 주문으로 존재 → 갭 안전, 기계적 자동 트리거.
- **명시된 의도**: "resting OCO = 항상 켜진 기계적 트리거, LLM intraday turn = 판단/조정 레이어. **LLM은 '가격이 레벨에 닿았는가' 부담을 지지 않는다.**" → 현재 구현은 정확히 이 금지된 일을 LLM으로 하고 있음. 이번 재설계는 이 의도를 실제로 구현하는 방향.

각 질문의 `[Answer]:` 태그 뒤에 선택지 문자를 적어주세요. 여러 개 선택이 가능한 문항은 그렇게 표시해 두었습니다(쉼표로 구분). 해당 선택지가 없으면 `X) 기타`를 고르고 설명을 적어주세요.

---

## Question 1 — LLM을 깨우는 사전 게이트의 성격
매 15분 틱마다 full LLM을 돌리는 대신, 무엇이 "추론할 가치가 있는 상태 변화"인지 먼저 판정하는 게이트를 둡니다. 이 게이트를 어떻게 구성할까요?

A) 순수 Python 결정형 게이트 — 깨울 조건(아래 Q2)을 Python이 판정, 충족 시에만 LLM turn 발화 (잠긴 "LLM은 가격감시 부담 안 짐" 의도와 일치, 비용·노이즈 최소) (추천)
B) 경량 LLM 1차 분류(저비용) → 필요 판단 시에만 본 turn (2단계 LLM)
C) 게이트 없이 매 틱 full LLM 유지하되, 구조화 brief 주입(Q4/B개선)만 적용
X) 기타 (please describe after [Answer]: tag below)

[Answer]: X. 현재 15분 intraday 유지. 다만 구조화를 더 잘하고, 뉴스나 trigger 없을땐 reasoning을 할게 없어 cheap하게 끝나고, 판단 필요할 경우 reasoning 후 결정하도록. 또, 특정 wake 조건 달성시 LLM을 실행 (15 intra day보다 우선.)

## Question 2 — LLM을 깨우는 wake 조건 (해당하는 것 모두, 쉼표로)
게이트가 어떤 이벤트에서 LLM turn을 발화할지. resting stop/target의 단순 "닿음"은 기계적 트리거가 처리하므로 기본 제외하고, **판단이 필요한** 이벤트 위주로 고릅니다.

A) 신규 체결 — 직전 turn 이후 broker에서 체결 발생(진입/보호선 체결 등)
B) 신규 뉴스 헤드라인 — 보유/감시 종목에 직전 turn 이후 새 헤드라인 등장
C) 비정상 움직임 — 일중 가격 이동 > 임계(예: 1.5×ATR) 또는 거래량 급증
D) 사전 등록된 discretionary watch-trigger 충족 (예: "SMA20 위 종가 시 stop tighten", "RTX $182 위 마감 시 ADJUST_STOP") — Q3에서 저장방식 결정
E) resting 보호선 체결/임박이 **thesis 재평가**를 요구하는 경우(단순 닿음이 아니라 손절 후 재진입 판단 등)
F) 장 마감 직전 1회 강제 발화(EOD 직전 점검 — 종가 기준 조건/그날의 watch 정리)
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A,C,D,E만. F는 비슷한 EOD 발화가 이미 있던걸로 기억됨. B는 어차피 intraday가 읽어들일것.

## Question 3 — discretionary watch-trigger 저장(구조화) 방식
Q2-D처럼 Python이 결정형으로 평가하려면, agent가 prose로만 쓰던 조건("$182 위 마감 시 tighten")을 기계가 읽을 구조로 남겨야 합니다.

A) 별도 구조화 파일 신설 — 예: `workspace/watch.jsonl` (agent가 append, Python 게이트가 읽어 평가; symbol/조건식/유효기간/연결 thesis) (추천)
B) 기존 `positions/<SYMBOL>.md`에 구조화 블록(YAML 프런트매터류) 추가 — 사람이 읽는 thesis와 한 파일에 공존
C) `Decision` 스키마에 `watch_trigger` 필드 확장 — decisions.jsonl 한 곳에 통합
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A.

## Question 4 — 계좌/체결 진실 반영 (account)
intraday에서 fill을 추론이 아닌 broker 진실로 확정하기 위해 `account`를 어떻게 쓸까요? (review.py의 outcome 조립 패턴 재사용 가능)

A) 깨어난 turn마다 Python이 account 스냅샷(보유/잔존 주문/체결)을 brief에 주입 → agent는 추론 대신 진실로 판단 (추천)
B) 신규 체결이 감지된 turn에만 account 주입
C) 프롬프트로 의무화 — agent가 매 (깨어난) turn에 직접 `account` 호출
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A

## Question 5 — 주입 brief의 범위 (재계산 제거)
깨어난 turn에 Python이 조립해 주입할 "intraday brief"에 무엇을 담을까요? (목적: agent가 매번 5종목 시세를 다시 긁고 거리 계산을 재수행하는 낭비 제거)

A) 종목별 현재가/세션 고저/거래량 페이스 + 플랜 레벨(stop/target/진입/watch-trigger) + 각 레벨까지 거리 + account 스냅샷 + "직전 turn 대비 델타(무엇이 바뀌었나)" — 풀 brief (추천)
B) 가격/델타/플랜 레벨까지만 (account는 Q4 정책대로 별도, 거래량/페이스 제외)
C) 최소 — 가격과 트리거된 wake 조건만 알려주고 나머지는 agent가 도구로 직접 확인
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A

## Question 6 — 뉴스 점검 빈도/비용 (죽은 촉매 분기 살리기)
intraday에서 뉴스를 보는 방식. 비용(매 종목 뉴스 호출)과 적시성의 균형.

A) 깨어난 turn에서, **직전 turn 이후 신규 헤드라인 diff만** 주입(중복 헤드라인 무시) — diff 감지는 Python의 가벼운 폴링 (추천)
B) 비정상 움직임(가격/거래량 급변) 때만 뉴스 호출 — 가격이 먼저 움직였을 때만 원인 탐색
C) 매 15분 틱마다 Python이 헤드라인을 가볍게 폴링해 변화만 게이트로 전달
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A

## Question 7 — cadence(스케줄) 변경 범위
"15분 고정"의 비효율(조용할 땐 과하고 마감 직전엔 느림)을 어떻게 다룰까요?

A) 15분 스케줄 틱은 유지하되 매 틱 Python 게이트 → 조건 충족 시에만 LLM 발화. 스케줄러 변경 없이 LLM cadence가 사실상 적응형이 됨 (가장 단순, 추천)
B) 스케줄러에 적응형 간격 — 모든 종목이 레벨에서 1×ATR 밖이면 간격을 넓히고(예 30분), 근접/고변동 시 좁힘(예 5분)
C) 시간대 기반 — 마감 전 구간(예 마지막 30분)만 5분, 그 외 30분
X) 기타 (please describe after [Answer]: tag below)

[Answer]: X. 위에서 답한것 처럼 15분 틱은 유지. 하지만 필요시 python trigger에 의해 LLM 우선 발화 가능. 더 빨라질 수 있는 적응형이 됨. 현재 비용 부담되는 수준은 아님.

## Question 8 — no-op(LLM 미발화) 틱의 기록
게이트가 LLM을 깨우지 않은 틱을 어떻게 남길까요?

A) `turns.jsonl`에 한 줄 heartbeat(게이트 평가 결과 + 거리표 요약)만 기록, LLM 호출 0 (관측가능성 유지 + 비용 0) (추천)
B) 아무것도 기록하지 않음(완전 스킵)
C) 가벼운 구조화 watch-state 스냅샷을 매 틱 기록(추세 추적용)
X) 기타 (please describe after [Answer]: tag below)

[Answer]: Q7의 답변에 의해 존재하지 않음.

## Question 9 — 조건부 ADJUST_STOP 처리 (advisor-only 경계)
"X 위 마감 시 stop을 tighten" 같은 조건부 액션을, 매 turn LLM이 기억으로 재평가하는 대신 어떻게 처리할까요?

A) Python 게이트가 조건 충족을 감지 → LLM을 깨워 ADJUST_STOP 여부를 판단·기록하게 함 (advisor-only 유지; Python은 감지만, 판단은 LLM) (추천)
B) 조건 충족 시 Python이 직접 ratchet ADJUST_STOP을 decisions.jsonl에 기록(LLM 우회) — 빠르지만 advisor-only 경계 약화 우려
C) 현행 유지 — 다음 turn LLM이 기억으로 재평가
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A. 위에서 말한 watch.jsonl로 이해하고 있음 (혹시 아니라면 알려주길)

## Question 10 — 빌드 단위와 내부 순서
5개 개선을 하나로 묶기로 했습니다(사용자 확정). 단일 유닛 구성과 내부 빌드 순서를 확인합니다.

A) 단일 유닛 `intraday-redesign`. 내부 순서: (1) 구조화 watch-trigger 스키마 + brief 조립(account+levels+delta) → (2) Python 결정형 게이트(wake 조건/뉴스 diff) → (3) prompts/orchestrator 주입 배선 → (4) cadence 게이팅 + no-op heartbeat → (5) 조건부 ADJUST_STOP 감지 연결 → 전체 회귀+신규 테스트 (추천)
B) 다른 순서/분할 선호 (설명)
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A. 4번에 no-op heartbeat는 없음

## Question 11 — 격리/검증 방식 (F2와 동일 패턴)
구현 격리와 검증 정책.

A) 새 git worktree+branch에서 구현, 전체 회귀(현행 ~196 테스트)+신규 테스트(결정형 게이트/brief 조립/watch-trigger 평가 등) 통과 후 머지. 라이브 trader(main)는 머지 전까지 무영향 (추천)
B) 기타 (please describe after [Answer]: tag below)

[Answer]: A

## Question 12 — 확장(Extension) 적용 확인
프로젝트 전역 설정(Security Baseline = Enabled, Property-Based Testing = Partial/Hypothesis)이 F1/F2에 일관 적용돼 왔습니다. F3에도 동일 적용할까요?

A) 동일 적용 — Security Baseline(SECURITY-03 로그에 비밀 금지 / -15 명시적 fail-closed 에러처리 등 해당분만), PBT Partial(순수함수: 게이트 조건 평가/거리 계산/watch-trigger 파싱에 Hypothesis 불변식) (추천)
B) 다르게 적용 (설명)
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A

---

# Part 2 — F2(human-steering-console)와의 통합/충돌 협의

**상황**: F2가 worktree(`feat/human-steering-console`)에서 **F3가 건드리려는 바로 그 컴포넌트들을 이미 재구조화**했습니다. 단순 파일 겹침을 넘어 *설계 중복*이 있어, F3 요구사항을 확정하기 전에 통합 방침을 정해야 합니다.

F2가 이미 만든 것 (실제 코드 확인):
- `prompts.py`: `human_context_block`(모든 turn 앞에 사람 지시/대기승인/최근개입 주입) + `reconcile_prompt`(사람 개입 직후 out-of-band turn).
- `orchestrator.py`: `AgentTradingLoop(coordinator=, steering=)`, `_with_human_context()`, `_run(acquire=)`로 **turn_lock** 획득, 신규 **`run_reconcile()`**.
- `steering/turns.py`: `TurnCoordinator`(turn_lock — `claude --resume`가 겹치지 않게 직렬화) + `ReconcileWorker`(트리거 디바운스 → 백그라운드 out-of-band turn, 다음 예약 turn보다 우선).
- `steering/bus.py`: `CommandBus`(단일 워커 스레드가 broker/executor/cursor mutation을 독점 — NFR-1; emergency 레인 2개).
- `steering/state.py`: `SteeringState` — `RunState`(paused/entries_halted), **broker `snapshot()` 캐시**(워커가 갱신), 락/대기승인/지시.

**핵심 통찰**: F3의 심장("매 틱이 아니라 *판단할 가치 있는 이벤트*에 LLM을 깨운다")은 F2의 `ReconcileWorker`(트리거 → 디바운스 → turn_lock 우선 out-of-band turn)와 **사실상 같은 메커니즘**입니다. F3의 wake 조건(체결/뉴스/watch-trigger)은 F2의 "사람이 개입함" 트리거의 형제입니다.

## Question CQ-A — F3의 설계 베이스/순서
F3를 어느 코드 형상 위에서 설계·구현할까요?

A) F2 브랜치 위에서(또는 F2 머지 후) F3 설계·구현 — post-F2 형상을 베이스로, F2의 동시성 모델(TurnCoordinator/ReconcileWorker/CommandBus/SteeringState)을 재사용. main 기준 설계는 F2 머지 시 무효화 위험이 큼 (추천)
B) F3를 main 기준으로 병렬 설계하고, 머지 시 공유 파일(orchestrator/prompts/modes.agent/scheduler)을 수동 통합
C) F2를 먼저 완전히 머지·검증한 뒤 F3 착수(순차, 충돌 최소·속도 느림)
X) 기타 (please describe after [Answer]: tag below)
나나
[Answer]: A. F2가 곧 initial 구현 끝나는데, 그 이후에 그 위에 구현.

## Question CQ-B — 이벤트 기반 LLM turn 메커니즘 (F3 게이트 ↔ F2 reconcile)
F3의 "이벤트→LLM 깨우기"를 F2의 백그라운드 turn 엔진과 어떻게 합칠까요?

A) F2의 ReconcileWorker/TurnCoordinator를 **일반화해 공유** — 트리거 소스만 추가(신규 체결/뉴스 diff/watch-trigger 충족). 단일 background-turn 엔진, turn_lock 하나, 중복 없음 (추천)
B) F3 전용 게이트/워커를 별도로 두되 **같은 turn_lock만 공유**(두 워커가 lock에서 경합)
C) F3 wake 이벤트를 그냥 **reconcile turn으로 흘려보냄**(전용 intraday-wake 프롬프트 없이 reconcile_prompt + brief 재사용)
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A

## Question CQ-C — account 스냅샷 출처 (NFR-1 단일워커 불변식 준수)
F3 brief에 넣을 계좌/체결 진실을 어디서 읽을까요? (F2 불변식: broker mutation+cursor는 CommandWorker만; 읽기는 캐시)

A) `SteeringState.snapshot()` 캐시를 읽음(워커가 갱신) — broker 직접 호출 안 함, NFR-1 유지 (추천)
B) 필요 시 `CommandBus.run(...)`으로 account 읽기를 워커에 제출(최신값 보장, 약간 느림)
C) F3가 스케줄러 스레드에서 broker를 직접 읽음 — NFR-1 완화, 비권장
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A

## Question CQ-D — pause/halt(RunState)와 F3 게이트의 상호작용
사람이 `/pause`(전체 정지)·`/halt-entries`(신규 매수 정지)한 상태에서 F3 게이트의 동작은?

A) 게이트가 매 평가에서 `run_state` 확인 — paused면 LLM wake 보류(heartbeat만 기록), entries_halted면 BUY를 유발하는 wake만 억제(보호선/ADJUST_STOP/SELL wake는 허용) (추천)
B) 게이트는 RunState 무시 — LLM은 깨우되 실제 행동은 F2 실행 게이트(executor)가 차단(불필요한 LLM 비용 발생 가능)
X) 기타 (please describe after [Answer]: tag below)

[Answer]: A
