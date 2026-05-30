# NFR Requirements (minimal) — Intraday 루프 재설계 (F3)

> Unit `intraday-redesign`. 깊이 = **minimal**(요구 NFR-1~6은 이미 requirements.md에 확정; 본 문서는 *기술스택·신규 의존성* 판정에 집중). 베이스 = main `src/agent/steering/`(F4) 위 worktree.

## 결론 (한 줄)
**신규 런타임 의존성 0.** stdlib(threading/queue/json/datetime) + 기존 deps(pydantic/loguru/APScheduler/alpaca-py/yfinance) 재사용 + Hypothesis(dev, 기존). NFR-1~6은 requirements.md에서 확정 — 본 stage는 추가 질문 라운드 없음.

## NFR 항목별 (requirements.md §7 ↔ 구현 수단)

| NFR | 내용 | 기술 수단(신규 dep 없음) |
|---|---|---|
| **NFR-1** turn 직렬화 | 모든 발화 turn_lock 경유; 스케줄=non-blocking skip, wake=우선 | main `TurnCoordinator`(stdlib `threading`) 재사용. ReconcileWorker는 **레인/타이머 수정**(critic#2) — `threading.Timer` 2개(또는 kind별) + wake-lane 타임아웃 단축. 신규 dep 없음 |
| **NFR-2** broker 접근 | account/fill은 snapshot 캐시; 워커스레드 broker 직접호출 금지 | main `SteeringRuntime.publish_snapshot`(5초 bus job) 재사용·**페이로드 확장**(체결 이벤트 키 추가). 시장데이터(quote/bars)는 데몬 `data_provider` 직접(C-7) |
| **NFR-3** 베이스·순서 | main 분기 worktree | git worktree(도구) — 코드 dep 아님 |
| **NFR-4** fault isolation | 감지/조립/폴링 예외가 데몬 비중단 | try/except + `loguru` 로깅(기존). best-effort 패턴(F4와 동일) |
| **NFR-5** 보안/PBT | SECURITY-03/15; 순수함수 PBT | `Hypothesis`(이미 dev dep, F2/F4에서 도입). SECURITY는 코드 규율 |
| **NFR-6** 검증 | 전체 회귀(현 **282** 수집) + 신규 단위/PBT | `pytest`(기존). agentic path backtest 비대상 |

## 신규 코드가 닿는 기존 의존성 (전부 설치됨 — 확인)
- **`alpaca-py` 0.43.2** — `get_fills`(activities)용. ⚠ **`GetActivitiesRequest`는 Trading 클라이언트에 없음**(Broker 클라이언트 전용). `TradeActivity` 모델 + `ActivityType.FILL` enum은 존재. → **구현 = `TradingClient.get("/account/activities", {...})` raw 호출**(베이스 `RESTClient.get` 상속) 후 `TradeActivity`로 파싱. **신규 dep 없음**, 단 타입 래퍼 없는 raw 호출이라 **paper 계정 대상 라이브 검증 항목**(NFR Design/Code Gen).
- **`yfinance`** — 뉴스 폴링(`news_provider` 재사용, 블로킹 → 별도 스레드). 신규 dep 없음.
- **`APScheduler`** — wake/스케줄 job. main scheduler 재사용(max_instances/coalesce 기설정).
- **`pydantic`** — 신규 레코드(WatchTrigger 등) 모델. main `records.py` 패턴 재사용.

## NFR Design으로 이월 (설계 결정 항목)
1. **ReconcileWorker 레인/타이머 구조**: wake-lane vs human-lane 분리 방식(별도 Timer 2개 vs kind별 dict-of-timer) + wake 타임아웃 값.
2. **snapshot 체결-이벤트 페이로드 형태** + activities `since` 커서 저장 위치(ByteCursor 재사용).
3. **abnormal-move 바 입력 캐시 주기**(1~5분) + 순수 ATR 계산 경계.
4. **brief 조립 스레딩**: BriefAssembler가 어느 스레드에서(스케줄 job / wake run_fn) 도는지 + snapshot/ data_provider 접근 규율.
5. **wake detector 루프 주기**(snapshot 5초 job에 합류 vs 독립) + 어디에 등록(scheduler vs bus job).
6. **`entry_inducing` 분류 위치**(WakeDetector 내부 순수함수) + fail-closed 기본값.
7. **fired-set `{et_date, fired_ids}` 영속 파일** 위치/형식 + daily_sweep 합류 지점.

## 미해당(N/A)
- 신규 클라우드 인프라/DB/네트워크 서비스 없음(로컬 데몬). 성능 SLA는 "turn은 cheap화로 빨라지나 LLM 지연이 지배적" — 정량 목표 없음(비용 비관심, requirements §3). 확장성/멀티테넌시 N/A(단일 운영자 데몬).
