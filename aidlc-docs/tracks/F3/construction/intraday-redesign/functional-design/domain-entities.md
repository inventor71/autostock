# Functional Design — 도메인 엔티티 (Intraday 루프 재설계 F3)

> 기술-비종속 설계 문서. 베이스 = `main`의 `src/agent/steering/`(F4 엔진) 위에 분기한 worktree.
> 본 문서는 **무엇을 모델링하는가**를 정의한다(자료구조·필드·불변식·경계). 흐름은 business-logic-model.md, 규칙은 business-rules.md.
> 결정 근거: FD Part B 답변 — **Q1=A, Q2=A,B, Q3=A, Q4=A(i), Q5=A, Q6=A, Q7=B, Q8=B**.

---

## 0. 엔티티 지형도 (신규 vs main 재사용)

| 구분 | 엔티티 | 출처 |
|---|---|---|
| **신규(F3)** | E1 WatchTrigger, E2 IntradayBrief, E3 WakeEvent, E4 SnapshotDelta(FillDelta 포함), E5 NewsDiff, E6 AbnormalMoveSignal | 본 문서 |
| **재사용(main)** | RunState(paused/entries_halted/et_date), SteeringState/snapshot payload, ByteCursor, TurnCoordinator(turn_lock), ReconcileWorker(trigger kind=), gate_agent_decision | `src/agent/steering/*` — 경계만 명시, 본 트랙에서 신규 생성 아님 |

**advisor-only 불변(전 엔티티 공통)**: 어떤 신규 엔티티도 주문을 직접 발행하지 않는다. 결정은 `decisions.jsonl`→RiskManager→Broker 단일 게이트로만 흐른다. 신규 엔티티는 모두 **감지·조립·기록** 계층이다.

---

## E1 — WatchTrigger  (`workspace/watch.jsonl`, FR-1 / FR-5 / Q1=A, Q2=A,B)

agent(=`claude` 서브프로세스)가 **신규 저널링 도구 `watch set` / `watch clear`** 로 등록하는 구조화 감시 조건. Python 게이트가 읽어 평가·발화한다. agent는 `watch.jsonl`을 직접 쓰지 않는다(advisor-only 경계 — Q1=A; 도구가 append를 대행).

### 필드
| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str | 안정 식별자(예 `wt_<ulid>`); fired 커서·clear의 키 |
| `symbol` | str | 대상 종목 |
| `condition` | enum | **v1 어휘(Q2=A,B)**: `price_above` / `price_below` / `close_above` / `close_below` |
| `level` | float | 비교 가격 |
| `intent` | str | LLM이 발화 시 판단할 의도(예 `"ADJUST_STOP→tighten to 180"`); **제안일 뿐, 자동 적용 아님**(FR-5) |
| `thesis_ref` | str \| null | 연관 thesis/decision id(추적용) |
| `valid_until` | str(ET date) | 만료 ET 날짜; 경과 시 daily_sweep가 비활성화 |
| `created_ts` | str(ISO, UTC) | 생성 시각 |
| `status` | enum | `active` / `fired` / `cleared` / `expired` (파생; 저장은 append + 별도 커서) |

### fired 상태 추적 — 별도 구조 (⚠ critic#5)
"발화했음"은 **ByteCursor로 표현할 수 없다**. `ByteCursor`(`jsonl.py:67-84`)는 정수 바이트 오프셋만 저장 — *어디까지 읽었나*는 알지만 *어떤 id가 오늘 발화했나*는 모르고, **ET-date 리셋 훅이 없다**(오프셋을 0으로 되돌리면 active 트리거 전부 재발화, 유지하면 영영 재발화 불가). 따라서 두 가지를 분리한다:
- **읽기 위치** = `ByteCursor`(watch.jsonl 파싱 진행, restart-dedup). ← ByteCursor 재사용은 *여기까지만* 유효.
- **fired 상태** = **신규 영속 구조 `{et_date, fired_ids: set[str]}`**(별도 작은 JSON). 발화 시 id 추가, ET 자정 `daily_sweep`가 `et_date` 전환 시 `fired_ids` 초기화. "동일 트리거 하루 1회"는 이 set으로 보장.

### 불변식
- **append-only**: 수정은 없음. 상태 전이(fired/cleared/expired)는 본문 재기록이 아니라 위 **읽기 커서 + fired-id set**의 조합으로 표현한다.
- `condition`은 v1 4종 외엔 거부(파싱 단계, fail-closed). `vwap_cross`/`volume_spike`/`time_at`는 후속(Q2에서 제외).
- `close_above`/`close_below`는 **세션/바 마감** 기준("위 마감 시")이므로 즉시가가 아니라 마감 확정 바에서만 평가(BLM-4).
- torn-line 가드: 미완성 trailing line은 skip, 완전 라인만 커서 진행(`jsonl.read_complete_lines` 재사용, C-5).

### 경계
- **writer = agent subprocess**(도구 `watch set/clear`), **reader = daemon**(wake 감지기) → 진짜 교차-프로세스 append/read. 따라서 공유 완전-라인 리더 + 영속 커서 필수(재사용).

---

## E2 — IntradayBrief  (transient, FR-2 / Q4 / Q5 / Q6=A)

매 intraday LLM turn(스케줄 + wake)에 **Python이 조립**해 프롬프트에 주입하는 구조화 요약. 영속 저장 아님(매 turn 재생성). 목적 = agent의 재계산(quote×N 재호출, 같은 표 재서술) 제거.

### 구성(Q6=A — 컴팩트 구조화 텍스트 블록)
종목별 1~2줄. 렌더는 `review.outcome_lines`의 **levels-vs-price 포맷팅 형태만** 참고하되, **그 함수를 호출하거나 그 데이터 조립 방식(=`broker.get_position` 직접 호출)을 재사용하지 않는다**(critic#6: `review.py:42`가 broker를 직접 부름 → NFR-2 위반). 데이터는 snapshot 캐시 + 데몬 data_provider에서만 받아 *별도 포맷터*로 직렬화:

```
SYM  px=… sess H/L=…/…  vol=…(pace …×)  | stop=… (-1.2%)  tgt=… (+3.4%)  watch=close_above 182
```

| 섹션 | 필드 | 출처 |
|---|---|---|
| 시장 데이터 | 현재가, 세션 고/저, 거래량 페이스 | **데몬 `data_provider` 직접**(C-7: 시장데이터는 bus 불필요) |
| 플랜 레벨 | stop / target / entry / 등록 watch level + **각 레벨까지 거리(%)** | 플랜/저널 + E1 |
| account 스냅샷 | 보유 수량, 잔존 주문, **체결 진실** | **`SteeringState.snapshot()` 캐시만**(NFR-2; broker 직접 금지) |
| **사람 컨텍스트** | 활성 directive · 대기 승인(pending) · 종목 락 상태 | `SteeringState`(directives/pending/locks). **⚠ critic#1 신규 작업**: F4는 사람-컨텍스트(`_recent_context`)를 `run_reconcile`에만 주입(`runtime.py:75`), intraday/스케줄/wake turn엔 **미주입**. `_with_human_context`라는 prepend는 **존재하지 않음** → F3가 brief에 **직접 담아야** 함(재사용 아님) |
| 델타 | 직전 turn 대비 신규 체결·새 고저·레벨 근접 변화 | E4 SnapshotDelta |
| 뉴스 diff | 직전 turn 이후 신규 헤드라인만 | E5 NewsDiff(스케줄 turn에만; wake 트리거 아님) |

### 불변식
- account/fill 필드는 **오직 snapshot 캐시**에서 — 조립 중 broker를 직접 호출하지 않는다(NFR-2, 단일워커 불변식). `outcome_lines` 형태 재사용은 *문자열 포맷*에 한함(데이터 조립 아님).
- **사람 컨텍스트는 매 intraday/wake turn에 포함**한다(critic#1) — 없으면 wake/스케줄 turn이 사람이 방금 락한 종목을 모르고 재진입. 이건 F4가 안 해주는 신규 작업.
- 시장 데이터 부재(provider 실패) 시 해당 줄은 비우되 **brief 조립 자체는 실패하지 않는다**(NFR-4 fault isolation; brief 없는 turn이 brief 조립 예외로 데몬을 죽이면 안 됨).
- 비밀(토큰·키) 미포함(SECURITY-03).

---

## E3 — WakeEvent  (transient, FR-4 / Q5=A)

Python wake 감지기가 만들어 단일 wake turn으로 전달하는 **typed 이벤트**. Q5=A에 따라 debounce 창 안의 다수 WakeEvent는 **하나의 wake turn**으로 합쳐져(coalesce) 프롬프트에 사유 목록으로 나열된다.

### 필드
| 필드 | 타입 | 설명 |
|---|---|---|
| `kind` | enum | `new_fill` / `abnormal_move` / `watch_trigger` / `protective_reassess` |
| `symbol` | str | 대상 종목 |
| `reason` | str | 사람·LLM 읽기용 1줄 사유(예 `"META filled 50sh @ 631.2 (entry)"`, `"RTX close_above 182 met"`) |
| `payload` | dict | kind별 근거(체결 상세 / 이동폭·ATR배수 / 충족 WatchTrigger id / 보호선 체결 상세) |
| `detected_ts` | str(ISO) | 감지 시각 |
| `entry_inducing` | bool | **BUY를 유발하는 wake인가**(**Q7=A 결정**: `entries_halted`면 WakeDetector가 `entry_inducing=True`인 wake를 **발화하지 않음**[억제]. = 상승 abnormal-move + 진입성 watch 조건. new_fill·protective_reassess·SELL성 watch는 False → 항상 허용 — BR-11 참조) |

### 불변식
- `kind`는 위 4종으로 한정. **뉴스(B)는 wake가 아니다**(스케줄 turn brief가 읽음, FR-6) / **EOD 강제(F)는 기존 EOD turn 담당**.
- 단순 "가격이 레벨에 닿음"은 WakeEvent가 아니다 — 그건 거래소 resting OCO가 기계적으로 처리(잠긴 아키텍처 §4). wake는 **판단이 필요한** 이벤트만(손절 후 재진입 등).
- 합쳐진 WakeEvent들은 **단일 `wake` kind의 단일 run_fn**으로 ReconcileWorker에 전달(C-4 dict는 kind별 1 run_fn이므로, F3는 typed-event 버퍼를 그 run_fn 안에서 drain — BLM-2 참조).

---

## E4 — SnapshotDelta (FillDelta 포함)  (transient, FR-2 / FR-4-A / Q3=A, C-3 잔여)

직전 발행 snapshot 대비 **신규 체결/포지션/주문 변화**. new-fill wake(E3.kind=new_fill)와 brief 델타 줄의 입력.

### 구성
| 하위 | 필드 | 설명 |
|---|---|---|
| **FillDelta** | `symbol`, `qty`, `price`, `side`, `kind`(entry/protective), `fill_id`, `ts` | **broker 활동내역(activities) 이벤트**로 감지(Q3=A, 아래) |
| PositionDelta | `symbol`, `qty_before`, `qty_after` | snapshot positions diff(보조) |
| OrderDelta | `order_id`, `transition`(new/filled/canceled) | open_orders 소멸/등장 |

### Q3=A 결정 — 활동내역(activities) API 채택 (⚠ critic#3)
- **신규 broker 작업**: 기존 fills 소스 `_alpaca_fills`(`trades_log.py:26-66`)는 **주문 단위**(`get_orders(status=CLOSED)`, `filled_avg_price`/`filled_qty`)라 **건별 fill_id가 없고 부분체결이 안 보인다** — Q3=A의 "부분체결·OCO 체결·동일수량 교차 구분"을 **할 수 없다**. → broker 포트에 **`GetActivitiesRequest(activity_types=[FILL])` 기반 `get_fills(since)`**(건별 체결 이벤트 + 안정 `id`)를 **신규로** 추가한다(reuse 아님). 이것이 "진짜 체결 진실"을 주는 유일한 경로.
- 접근 경로 = **bus job → snapshot 페이로드 확장**(NFR-2). 감지기는 broker를 직접 호출하지 않고 snapshot의 fills 목록을 읽는다.
- main snapshot은 현재 positions+open_orders+market_open만 담는다(`runtime.publish_snapshot:102-123`); F3는 여기에 **신규 체결 이벤트 목록 + activities 커서(since)**를 추가한다(C-3 잔여). bus job 주기(현 5초, `agent.py:181` 검증됨)에 합류.

### 불변식
- 같은 `fill_id`(activity id) 재처리 금지(idempotent) — activities `since` 커서가 단조 전진. (주문 키가 아니라 **체결 이벤트 id** 기반이라 부분체결 두 건이 합쳐지지 않음.)
- 체결 진실은 broker 권위 — snapshot의 positions count·가격 추론으로 *대체*하지 않는다(현행 META 추론 버그 해소가 본 엔티티의 존재 이유).

---

## E5 — NewsDiff  (transient, FR-6 / Q8=B)

직전 turn 이후 **신규 헤드라인만** 추린 diff. 스케줄 turn brief에만 주입(wake 트리거 아님 — 지연 비치명적).

### 필드
| 필드 | 타입 | 설명 |
|---|---|---|
| `symbol` | str | 대상 종목 |
| `headlines` | list[str] | 직전 대비 신규 헤드라인 |
| `last_seen_key` | str | per-symbol 마지막 헤드라인 키(중복 제거용, **영속**) |

### Q8=B 범위/주기
- 범위 = **보유 + watch 등록 종목**(감시 종목의 촉매도 thesis 재평가에 유용).
- 주기 = 별도 폴링 스레드/bus job, TTL ≥ 15분(`news_provider` 기존 15분 캐시 존중 — 더 잦게 폴링해도 캐시가 입도를 15분으로 제한).
- per-symbol `last_seen_key` 영속(재시작/turn 간 중복 헤드라인 무시).

### 불변식
- 폴링은 best-effort(NFR-4) — 레이트리밋/예외가 데몬·brief를 죽이지 않음.
- diff가 비면 brief의 뉴스 섹션은 생략(빈 줄 없음).

---

## E6 — AbnormalMoveSignal  (transient, FR-4-C / Q4=A(i))

abnormal-move wake(E3.kind=abnormal_move)의 판정 결과.

### 판정 기준 (Q4=A)
| 입력 | 임계 | 출처 |
|---|---|---|
| 일중 `|가격이동|` | `> k × ATR(14)` (기본 k=1.5) | 데몬 data_provider(시장데이터 직접, C-7) |
| 거래량 | `> m × 평균` (기본 m=3) | 데몬 data_provider |

둘 중 **하나** 충족 시 신호.

### 설정 위치 (Q4=(i))
`config/settings.yaml`의 **신규 `intraday:` 블록**:
```yaml
intraday:
  abnormal_move:
    atr_k: 1.5
    vol_multiple: 3.0
    atr_period: 14
```
- 리터럴 코드 상수 아님(외부 튜닝 가능) — 단, 블록 부재 시 위 기본값으로 fail-safe.

### ⚠ 입력 fetch 비용 (critic#7)
ATR(14)는 종목별 **intraday OHLC 14+ 바**가 필요하다. data_provider는 `get_bars(timeframe)`를 제공하지만(`alpaca_provider.py:41`, `yfinance_provider.py:33`) **캐시가 없고**, yfinance intraday는 레이트리밋·coarse(`yfinance_provider.py:86-89`). 매 5초 감지 루프마다 보유+watch 종목 전부의 14-바를 다시 끌면 블로킹·throttle. → 설계 분리:
- **바 입력 캐시**: ATR/평균거래량 입력 바를 **1~5분 주기**로 갱신(감지 틱마다 fetch 아님), best-effort(실패 시 직전 값 유지, NFR-4).
- **순수 ATR/판정 계산**: 캐시된 바에서 ATR·평균·임계 비교 — 이 부분만 순수 함수(PBT 대상).

### 불변식
- ATR/평균거래량/임계비교(=계산부)는 **순수 함수**(PBT 대상, NFR-5): 동일 입력 → 동일 신호, 임계 경계에서 단조. *입력 fetch는 분리*(위).
- 시장데이터 입력이므로 bus 불필요(C-7) — broker 접근 아님.

---

## 재사용 엔티티 경계 (신규 생성 금지 — main `src/agent/steering/`)

| 엔티티 | main 위치 | F3가 쓰는 면 |
|---|---|---|
| **RunState** | `state.py` (`paused`, `entries_halted`, `et_date`) | wake 게이팅(FR-7): paused→발화 보류; **entries_halted→Q7=A: WakeDetector가 `entry_inducing` wake를 발화 억제**(gate는 entries_halted 무관여 — critic#4). `set_entries_halted` 존재(`state.py:146`)하나 소비자 없음 → **소비 훅 신규** |
| **snapshot payload** | `runtime.publish_snapshot:102-123` (positions/open_orders/market_open/locked) | E2 account·E4 fills 입력원; **F3는 체결 이벤트 목록+activities 커서 추가**(atomic write·5초 job 유지) |
| **ByteCursor** | `jsonl.py:67-84` | watch.jsonl·activities **읽기 위치**의 영속 메커니즘. ⚠ **fired 상태/날짜 스코프엔 부적합**(정수 오프셋만) — E1의 별도 `{et_date, fired_ids}` 사용 |
| **TurnCoordinator** | `turns.py:37` (`try_scheduled_turn`/`reconcile_turn`) | 스케줄=skip-if-busy(C-1 기이행), wake=reconcile_turn 봉투 |
| **ReconcileWorker** | `turns.py:82-114` (`trigger(run_fn, kind=)`) | wake용 단일 `wake` kind. **⚠ critic#2**: debounce 타이머가 **kind 공유**(`turns.py:99-101`)·`_fire` 순차(`:110`) → 잦은 wake가 사람 `human` reconcile을 굶김. → **kind별(또는 human/wake 레인 분리) 타이머** + typed-event 버퍼는 **WakeDetector 소유**(발화 시점 drain, dict에 안 넣음)로 수정 필요(순수 재사용 아님) |
| **gate_agent_decision** | `gate.py:33-49` | 변경 없음 — 사람-락 게이트(advisor-only). **entries_halted/paused는 다루지 않음**(`gate.py:8` 명시) → Q7=A 억제는 detector 책임 |
