# NFR Design — 논리 컴포넌트 (Intraday 루프 재설계 F3)

> Unit `intraday-redesign`. 신규 모듈 + 기존 파일 수정 목록(코드 아님 — 경계·시그니처·책임). 베이스 = main 분기 worktree.

## 신규 모듈 (`src/agent/intraday/`)
| 모듈 | 책임 | 핵심 진입점(초안) | 의존 |
|---|---|---|---|
| `records.py` | F3 레코드(pydantic) | `WatchTrigger`, `WakeEvent`, `FillDelta/SnapshotDelta`, `NewsDiff`, `AbnormalMoveSignal` | pydantic |
| `watch_store.py` | watch.jsonl 리더 + fired-set | `WatchStore.active() -> list[WatchTrigger]`(읽기 ByteCursor), `.mark_fired(id)`, `.is_fired(id)`, `.sweep(et_date)` | `steering/jsonl.py`(read_complete_lines/ByteCursor/atomic_write_text) |
| `bars.py` | 바 입력 캐시 + 순수 지표 | `BarCache.get(symbol) -> bars`(60s stale), `atr(bars,14)`, `avg_volume(bars)` (순수) | data_provider |
| `abnormal.py` | abnormal-move 판정(순수) | `detect_abnormal(symbol, price, bars, cfg) -> AbnormalMoveSignal|None` | bars.py |
| `brief.py` | IntradayBrief 조립 + 렌더 | `BriefAssembler.build(symbols, *, snapshot, state, news, include_news) -> str`. **held 종목은 snapshot positions에서**(orchestrator.held_symbols=broker 호출이므로 미사용, 2차 critic#6). snapshot 비면 account 섹션 생략(fail-closed) | data_provider(캐시), **in-proc last_snapshot**(읽기), state(읽기) |
| `news_diff.py` | 뉴스 폴링 스레드 + diff | `NewsPoller.start()/stop()`, `.diff_for(symbols) -> dict[sym,NewsDiff]`, `.last_seen` 영속 | news_provider(yfinance), threading |
| `wake.py` | wake 감지 + 트리거 | `WakeDetector.detect_wakes()`(스케줄 5초 호출), 버퍼 소유, `classify_entry_inducing(ev)`(순수), RunState 게이팅 | watch_store, abnormal, snapshot, state, ReconcileWorker |
| `prompts_intraday.py`*(또는 prompts.py 확장)* | brief 기반 프롬프트 | `intraday_prompt(brief, held)`, `wake_prompt(brief, events)` | — |

\* 단순하면 기존 `src/agent/prompts.py`에 함수 추가로 흡수(모듈 신설 대신).

## agent 도구 (Q1=A — `watch set/clear`)
- `src/agent/tools/`에 신규 verb: `watch set <SYM> <condition> <level> [intent] [until]` / `watch clear <id>` / `watch list`.
  - 검증 후 `workspace/watch.jsonl`에 **append-only**(도구가 유일 writer; agent 직접 파일쓰기 아님 — BR-6.1).
  - 조건 v1 4종(`price_above/below`,`close_above/below`) 외 거부(fail-closed).
  - 기존 tools 등록 패턴(`agent/tools/__main__.py`/스키마) 재사용.

## broker 포트 확장 (Q3=A, critic#3)
| 파일 | 변경 |
|---|---|
| `src/execution/base.py` *(2차 critic#8 — `brokers/base.py` 아님)* | `BaseBroker.get_fills(since: str|None) -> list[FillEvent]` 추가, **concrete no-op 빈 리스트**(get_open_orders/record_trade_ledger와 동형 비-abstract 기본 → SimulatedBroker 안 깨짐, 확인됨) |
| `src/execution/brokers/alpaca_broker.py` | override: `self._client.get("/account/activities", {"activity_types":"FILL","after":since,...})`(경로에 `/v2` 금지 — get이 prepend) → `TradeActivity` 파싱 → `FillEvent`(symbol/qty/price/side/id/ts/kind). 페이지네이션·ET 타임존 처리. **R1 paper 검증이 권위**(monkeypatch 단위테스트는 가정 형태) |

> `record_trade_ledger`(U4) 패턴과 동형: base no-op + Alpaca override → 호출부 broker-agnostic.

## 기존 파일 수정 (main)
| 파일 | 수정 | 근거 |
|---|---|---|
| `src/agent/steering/turns.py` | `ReconcileWorker` per-kind 타이머(`dict[str,Timer]`, 무한-취소 굶김만 해소) + `_fire`가 **human-kind 먼저 dispatch**(2차 critic#1) + kind→acquire-timeout을 `reconcile_turn(timeout=)`에 **실제 전달**(현재 `turns.py:112` 미전달, 2차 critic#2). ⚠ 실행(LLM) 제한은 turn-level timeout 필요(`_run(timeout=)`) | P1 |
| `src/agent/steering/runtime.py` | `publish_snapshot` 페이로드 `fills` + `.fills.cursor` 증분(bus 워커 위 `get_fills`); **`last_snapshot` in-proc dict 노출**(brief가 파일 아닌 메모리 읽기, 2차 critic#4) | P2/P4 |
| `src/agent/orchestrator.py` | `run_intraday(brief: str)` 인자 수용; 신규 `run_wake(brief, events)`(`_run`에 turn_type/prompt + wake `timeout` 전달); **brief/wake 경로 held는 snapshot에서**(held_symbols=broker 호출 미사용, 2차 critic#6) | BLM-1/2, critic#8 |
| `src/agent/prompts.py` | `intraday_prompt`가 brief 수용; `wake_prompt` 추가; **human-context를 brief에 포함**(별도 prepend 없음) | critic#1/#8 |
| `src/trading/modes/agent.py` | `_intraday`가 BriefAssembler로 brief 만들어 `run_intraday`에 전달; **`agent_wake` 5초 job 등록** + seconds-job `misfire_grace_time`; `entries_halted` 소비(detector); NewsPoller 시작/정지. **steering=None이면 레거시 `intraday_prompt(quotes,held)` 폴백**(brief/wake/news 비활성, 2차 critic#7) | BLM-3/7, P7 |
| `src/trading/scheduler.py` | seconds-job `misfire_grace_time` 지정(+필요 시 전용 executor) — coalesce 틱 누락 인지 | P5, 2차 critic#3 |
| `config/settings.yaml` | 신규 `intraday:` 블록(`abnormal_move.atr_k/vol_multiple/atr_period`, `wake.detect_seconds`, `news.ttl_minutes`, `bars.cache_seconds`, `price.cache_seconds`) | Q4(i) |

## 데이터 스토어 (workspace/, 신규)
| 파일 | 내용 | 쓰기 | 읽기 |
|---|---|---|---|
| `watch.jsonl` | WatchTrigger append-only | `watch` 도구(agent 프로세스) | WatchStore(데몬) |
| `.watch.cursor` | watch.jsonl 읽기 바이트 오프셋 | WatchStore | WatchStore |
| `watch_fired.json` | `{et_date, fired_ids}` | WatchStore.mark_fired / sweep | WatchStore |
| `.fills.cursor` | 마지막 activity 시각/id | publish_snapshot(bus) | publish_snapshot |
| `.news_seen.json` | per-symbol last_seen_key | NewsPoller | NewsPoller |
> 모두 `atomic_write_text`(`channel.py`) 사용. heartbeat/보류는 별도 파일 없이 loguru(C-1: 정상 운영 heartbeat 없음, paused만 보류 로그).

## 검증 항목 (Code Gen / Build&Test)
- **R1**: `get_fills` raw GET — paper 계정에 실주문 후 activities로 체결이 잡히는지, 페이지네이션/타임존, 부분체결 분리. (실패 시 주문상태 degrade 경로.)
- **V2**: ReconcileWorker per-kind 타이머 — wake 폭주 중 human reconcile이 안 굶는 통합테스트.
- **V3**: skip-if-busy — wake turn 실행 중 15분 슬롯 도래 → 스케줄 스킵(큐잉 아님). (main 동작 회귀 보호.)
- **V4**: fired-set ET-date 롤오버 — sweep 후 active 트리거 재발화 / 같은 날 재발화 금지.
- **V5**: entries_halted — `entry_inducing` wake 억제, 그 외 wake/스케줄 정상.
- **V6**: 전체 회귀 282 + 신규 단위/PBT 그린.

## PBT 대상 (Hypothesis)
`atr`/`avg_volume`/`detect_abnormal`(임계 단조), 레벨 거리(%), watch 조건 평가(경계), `classify_entry_inducing`(fail-closed), activities/fired 커서 단조·idempotency.
