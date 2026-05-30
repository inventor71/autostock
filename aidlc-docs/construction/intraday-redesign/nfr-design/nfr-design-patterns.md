# NFR Design — 패턴 (Intraday 루프 재설계 F3)

> Unit `intraday-redesign`. F2/F4의 P1–P6를 F3에 적응 + critic 수정 반영. 이월 7항목 전부 해소(문서 끝 표).
> 베이스 = main `src/agent/steering/`(F4). 신규 dep 0.

## P1 — Turn 직렬화 + ReconcileWorker 레인 (NFR-1, critic#2 / 2차 critic#1·#2)
- 모든 LLM 발화는 main `TurnCoordinator` 경유: 스케줄=`try_scheduled_turn`(skip-if-busy), wake=`reconcile_turn`(우선·bounded-blocking).
- **ReconcileWorker 수정(순수 재사용 아님)**:
  - **(a) per-kind 타이머**(`dict[str, threading.Timer]`): 현재 debounce 타이머가 kind 공유(`turns.py:99-101`)라 잦은 `wake`가 `human` 타이머를 **반복 취소→무한 지연**시킨다. per-kind 타이머가 이 **무한-취소 굶김**을 없앤다. ⚠ **단, 이게 굶김을 "해소"하는 건 아니다(2차 critic#1)**: 굶김의 본질 지점은 타이머가 아니라 **단일 `turn_lock`**. `_fire`가 한 스레드에서 `reconcile_turn`을 순차 호출(`turns.py:110-112`)하고 wake LLM이 lock을 잡고 도는 동안 human reconcile은 대기한다 — **in-flight wake turn 1회분 대기는 본질적·선점 불가**(NFR-1 단일 lock, bus BR-13과 동일 성질, CQ-R1의 "max-staleness=in-flight turn 잔여"와 일치).
  - **(b) `_fire` 우선순위 정렬**: 한 배치에 `human`과 `wake`가 같이 있으면 **`human`을 먼저 dispatch**(사람 개입 우선). 그래도 직전에 시작된 in-flight turn은 못 끊는다.
  - **(c) 타임아웃 정정(2차 critic#2)**: `reconcile_turn(timeout=)`은 **획득 타임아웃**일 뿐 실행을 끊지 못한다(`turns.py:53,70` — run_fn은 무제한). `_fire`는 현재 timeout을 **전달조차 안 한다**(`turns.py:112`). → "wake 120s로 점유 제한"은 **불가**. 실행을 실제로 bound하려면 LLM **세션 호출 레벨 timeout**(`_run(timeout=)`, orchestrator.py)을 wake 경로에 넘겨야 함 = 신규 plumbing(Code Gen Step 8/9). 그 전엔 wake hold는 LLM turn 길이만큼.
- **버퍼 소유권**: typed-event는 `_pending[kind]`(최신 1개만 유지)에 넣지 않고 **WakeDetector가 소유한 버퍼**에 쌓고, wake run_fn이 **발화 시점에 drain**(critic#2). `kind="wake"` 한 종류로 묶어 Q5=A coalesce 달성.

## P2 — 브로커 접근 격리: snapshot-only account/fills, market-direct (NFR-2, C-7, critic#3/#6 / 2차 critic#4·#5·#6)
- **in-proc snapshot 캐시(2차 critic#4)**: main `publish_snapshot`은 `snapshot.json`을 **쓰기만** 한다(`channel.py:178-181`, in-proc getter 없음). brief가 매 turn 파일을 재파싱하면 디스크 왕복+staleness. → **`SteeringRuntime`에 `last_snapshot` in-proc dict 추가**(bus 워커가 publish 시 채움), brief/감지기는 그걸 읽는다. 비었으면(첫 publish 전) **fail-closed: account 섹션 생략하고 진행**.
- **account·체결**: 위 `last_snapshot`에서만. F3는 페이로드에 **`fills`(신규 체결 이벤트) + activities 커서**를 추가 — broker 조회는 **bus 워커 안에서만**(`get_fills`도 `publish_snapshot._build`가 `bus.submit`로, `runtime.py:98-125`).
- **⚠ fills freshness 한계(2차 critic#5)**: get_fills가 bus 워커에 있으면 단일워커 불변식은 지키나, **emergency 레인/긴 executor 배치가 워커를 점유하면 snapshot+fills publish가 그 뒤에 큐잉**(`bus.py` 우선순위 큐) → new_fill wake가 bus 백로그만큼 지연/coalesce 누락 가능. **수용 결정**: stop/target 보호는 거래소 resting OCO가 기계적 처리하므로 **체결 *인지*가 수 초 늦어도 안전엔 영향 없음**(판단 wake만 지연). 따라서 bus-on 유지(불변식 우선), staleness는 bus 백로그로 bound됨을 명시. *(이견 시 read-only fills를 별도 스레드로 빼는 대안 — NFR-2 문구와 충돌하므로 기본 비채택.)*
- **`held_symbols` broker 호출 차단(2차 critic#6)**: `orchestrator.held_symbols()`는 `portfolio_provider()`→broker를 turn 스레드에서 직접 부른다(`orchestrator.py:62-70`). F3 brief/wake 경로는 **held 종목을 snapshot positions에서** 도출(orchestrator.held_symbols 사용 금지) — 그래야 "broker 직접호출 0"이 실제로 성립.
- **`outcome_lines` 금지**(critic#6): 그 함수는 `broker.get_position` 직접 호출 → brief는 *포맷만* 본뜬 별도 포맷터를 쓰고 데이터는 last_snapshot+data_provider.
- **시장데이터**(quote/bars/지표): 데몬 `data_provider` 직접(C-7 — bus 불필요, broker 아님). **단 감지 스레드 블로킹 주의는 P5/동시성표 참조**.
- **`get_fills` = raw activities GET**: alpaca-py TradingClient에 typed 래퍼 없음 → `_client.get("/account/activities", {"activity_types":"FILL","after":<cursor>})` + `TradeActivity` 파싱(경로에 `/v2` 붙이지 않음 — get이 버전 prepend, 2차 critic#9). **paper 라이브 검증 항목**(R1; monkeypatch 단위테스트는 *가정* 형태라 green이어도 실제와 다를 수 있음 — R1이 권위). 실패 시 주문상태 전이로 degrade(부분체결 맹목, fail-closed).

## P3 — Fault isolation: best-effort 데몬 보호 (NFR-4)
- WakeDetector.detect / BriefAssembler.build / NewsPoller / WatchStore 평가 = 전부 try/except + loguru, 예외는 삼키고 계속(F4 패턴). 감지 실패가 스케줄 turn·데몬을 죽이지 않음.
- brief 섹션 부분 실패 → 그 줄만 공백, turn 진행. activities GET 실패 → 직전 커서 유지, new_fill wake 그 틱 스킵(다음 틱 재시도).

## P4 — 영속: 읽기 커서 + fired-set + activities 커서 (critic#5)
- **watch.jsonl 읽기**: main `jsonl.read_complete_lines` + `ByteCursor`(`workspace/.watch.cursor`) — torn-line 가드, restart-dedup. *읽기 위치 전용*.
- **fired 상태**: **별도 `workspace/watch_fired.json` = `{et_date, fired_ids:[...]}`**, `atomic_write_text`. 발화 시 id 추가; `daily_sweep`(0:01 ET, 기존 job)가 `et_date` 롤오버 시 `fired_ids` 비움. ByteCursor는 0으로 안 되돌림(append-only 단조).
- **activities 커서**: 마지막 처리 activity의 시각/id를 작은 json(`workspace/.fills.cursor`)에 atomic 저장. publish_snapshot이 `after=cursor`로 증분 조회 → 단조 전진, activity id로 dedup(부분체결 미합산).
- **news last_seen**: per-symbol 마지막 헤드라인 키를 `workspace/.news_seen.json`에 영속(중복 제거).

## P5 — 입력 fetch ≠ 순수 계산 분리: 바·가격 캐시 (critic#7 / 2차 critic#3)
- **감지 스레드 비블로킹 강제(2차 critic#3)**: `detect_wakes`는 `BackgroundScheduler` 기본 풀(10 스레드, `scheduler.py`)의 5초 job. **동기 네트워크 호출이 5초를 넘기면 `coalesce=True`가 wake 틱을 조용히 누락**시킨다. → detect_wakes는 **캐시된 시장데이터만** 읽는다: BarCache(아래) + **가격도 단기 TTL 캐시**(예 2~3초; `get_latest_price`를 매 틱 동기 호출하지 않음). 신선 fetch는 캐시 갱신 잡(또는 BarCache 내부)이 담당하고, 감지 루프 자체는 메모리 읽기+순수 계산만.
- **스케줄러 헤드룸**: wake/snapshot 등 seconds-job에 **명시적 `misfire_grace_time`** 설정 + (필요 시) 전용 executor 분리 검토. coalesce가 틱을 떨구는 동작을 설계로 인지(누락돼도 다음 틱 재평가 — best-effort).
- **BarCache**: per-symbol `(bars, fetched_ts)`; `get_bars`가 stale(>cadence, 기본 **60s**)일 때만 재fetch, best-effort(실패 시 직전 값). 5초 감지 틱마다 14-바 재fetch 금지.
- **순수 계산**: ATR(14)/평균거래량/임계 비교·레벨 거리(%)·watch 조건 평가·`entry_inducing` 분류 = **부수효과 없는 순수함수**(PBT 대상). 입력(바/가격/스냅샷)은 주입.

## P7 — steering=None degrade (NFR-8, 2차 critic#7) — *결정*
F3 전 기능(snapshot/wake/ReconcileWorker/RunState)은 `steering`에 의존한다. `--steering` 없이 데몬이 돌면(NFR-8 지원 구성):
- **`_intraday`는 레거시 경로로 폴백**: 기존 `intraday_prompt(quotes, held)`(brief 없음), wake/news/account 섹션 전부 비활성. wake job·NewsPoller 미등록.
- 즉 **F3 개선은 steering-on에서만 활성**, steering-off는 "이전과 동일"(NFR-8 유지). *(이견 시 — 예: F3를 steering 필수로 못박기 — 알려주세요. 기본은 레거시 폴백.)*

## P6 — 보안 / fail-closed (NFR-5, SECURITY-03/15)
- brief·로그·watch·heartbeat에 비밀 미포함; activities 응답 계정 식별자 로그 스크럽.
- 알 수 없는 watch 조건·activities 파싱 실패·`entry_inducing` 분류 모호 → **보수 처리**(watch 거부 / new_fill 보류 / 억제 쪽 True). 임의 진행 금지.

## 동시성 모델 (스레드별 책임)
| 스레드 | 도는 것 | broker | 시장데이터 | turn_lock |
|---|---|---|---|---|
| APScheduler `agent_intraday`(15분) | `_intraday`→brief 조립→`_scheduled_turn(run_intraday(brief))` | 안 함(last_snapshot) | 캐시(BarCache/가격TTL) | `try_scheduled_turn` |
| APScheduler `agent_wake`(신규, 5초) | `detect_wakes`(캐시 읽기+순수계산) → 버퍼+`ReconcileWorker.trigger(kind="wake")` | 안 함(last_snapshot) | **캐시만**(동기 fetch 금지, P5/critic#3) | 안 잡음(트리거만) |
| APScheduler `steering_snapshot`(5초) | `publish_snapshot`(+fills, last_snapshot 갱신) | **bus 워커 위에서만** | — | — |
| ReconcileWorker Timer(wake-lane) | wake run_fn: 버퍼 drain→brief→`wake_prompt`→`reconcile_turn` | 안 함 | 캐시(BarCache/가격TTL) | `reconcile_turn`(우선) |
| NewsPoller(신규 데몬 스레드) | per-symbol 뉴스 폴링 diff | 안 함 | yfinance 직접 | — |
| bus single-worker | executor·publish_snapshot·`get_fills` | **유일 mutation/조회 지점** | — | — |

→ broker 조회(`get_fills` 포함)는 **bus 워커 1곳**, 시장데이터는 감지/조립 스레드 직접, LLM 발화는 turn_lock 1곳. NFR-1/NFR-2 불변식 유지.

## 이월 7항목 해소
| 이월 | 해소 |
|---|---|
| 1 ReconcileWorker 레인/타임아웃 | P1 — per-kind 타이머 + wake 120s + WakeDetector 소유 버퍼 |
| 2 snapshot fills 페이로드 + 커서 | P2/P4 — `fills` 키 추가, `.fills.cursor` atomic, bus 워커 조회 |
| 3 바 캐시 주기/순수 경계 | P5 — BarCache 60s + 순수 계산 분리 |
| 4 brief 조립 스레딩 | P2/동시성표 — run_fn 안(스케줄/ wake 스레드), snapshot+data_provider만 |
| 5 wake detector 주기/등록 | 동시성표 — `add_seconds_job(detect_wakes, 5, "agent_wake")`, 트리거만(논블로킹) |
| 6 entry_inducing 위치 | P5/P6 — WakeDetector 순수 분류함수, fail-closed True |
| 7 fired-set 위치/형식 | P4 — `watch_fired.json{et_date,fired_ids}` + daily_sweep 합류 |
