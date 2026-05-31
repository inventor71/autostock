# F14 NFR Design

## A. 타임아웃 주입 경로 (확정 — alpaca-py 0.43.2 실측 기반)
SDK가 timeout 파라미터를 노출하지 않으므로 **requests.Session 레벨에서 강제**한다.

- 헬퍼 `_install_session_timeout(client, connect=3.0, read=5.0)`:
  대상 클라이언트의 `requests.Session`(현 버전: `client._session`)의 `request` 메서드를 래핑하여
  호출자가 `timeout`을 주지 않은 경우 `timeout=(connect, read)`를 주입. 이미 지정돼 있으면 존중.
- 적용 (총 **3개** 클라이언트 — critic R1[HIGH], R2[MEDIUM] 정밀화):
  - `AlpacaBroker.__init__`: `self._client`(TradingClient) 생성 직후.
  - `AlpacaBroker.get_latest_prices`: **`if self._data_client is None:` 블록 내부, lazy 생성 직후**
    (`alpaca_broker.py:363-365`). ⚠️ ctor엔 없으므로 ctor 훅으로 안 닿음 — 반드시 이 블록 안에서 래핑.
    블록 내부이므로 최초 1회만 실행 → 이 경로엔 이중 래핑 없음. 호출자 `runtime.py:298` **단일**(확인)이라
    lazy-init 레이스 없음. **멱등 가드 근거(R3 정정)**: 이 경로가 1회라서가 아니라, **동일 헬퍼를 3개
    클라이언트에 적용**하고 테스트/재생성 시 wrapper가 wrapper를 또 감싸 read 타임아웃이 중첩되는 걸
    막으려는 것. 식별은 wrapper에 마커 속성(예: `__autostock_timeout_wrapped__`)을 달아 검사(단순
    `_session` 존재 체크로는 매번 재래핑됨).
  - `AlpacaDataProvider.__init__`: `self._client`(StockHistoricalDataClient) 생성 직후.
- **방어성(SECURITY-11/15)**: `_session` 속성이 없거나 구조가 바뀐 SDK 버전이면 헬퍼는 경고 로그 후
  **graceful no-op**(생성 자체는 실패시키지 않음) — 단, 그 경우 타임아웃 미적용이므로 worktree
  live-verify에서 실제 타임아웃 적용 확인을 수용 기준으로 둔다.
- 값은 broker/provider ctor 인자로 노출(하드코딩 회피, 향후 튜닝 가능).

## B. prefetch 워커 설계
- **위치**: 기존 패턴(steering_* seconds job)과 동일하게 **APScheduler seconds job** `agent_prefetch`로
  등록(5s). bars는 같은 job 안에서 `bars_ttl(60s)` 경과 심볼만 재요청(가격은 매 5s).
  - 근거: BackgroundScheduler는 ThreadPoolExecutor(**기본 max_workers=10**, critic 확인)라 prefetch가
    블록돼도(타임아웃으로 bounded) detect_wakes·publish_snapshot 등 다른 job은 별 스레드에서 진행.
    prefetch가 가는 곳은 `BarCache._dp` = `data_provider`(broker 아님, `modes/agent.py:83`)이므로
    CommandBus(단일 broker mutation writer)와 분리됨(NFR-2).
  - prefetch job도 `_JOB_DEFAULTS`(max_instances=1, coalesce) 적용 → 스스로 겹치지 않음.
  - **⚠️ 풀 여유 (critic LOW)**: 현 seconds job 8개 + agent_prefetch 1개 = 9 ≤ 10. 여유 1슬롯뿐.
    daily/open/close cron 동시 발화 시 일시 초과 가능(misfire_grace_time=30s로 흡수). → `scheduler.py`
    ThreadPoolExecutor `max_workers`를 **16으로 상향**(저비용 하드닝, 향후 job 추가 대비).
  - **⚠️ BarCache 멀티-writer 문구 정정 (critic LOW)**: BarCache(`_bars`/`_price` dict)는 락이 없고
    원래부터 멀티-writer(BriefAssembler get_* + 이제 prefetch). GIL이 `(ts,value)` 튜플 단일 대입/조회의
    원자성을 주므로 안전하나, "단일 writer로 분리"가 아니라 "GIL-원자 dict 연산에 의존하는 멀티-writer
    캐시에 writer 하나 추가"가 정확한 표현. 복합 연산을 넣지 말 것.
- **심볼 소스**: `held_and_watched(steering.last_snapshot, watch_store)` (기존 `_intraday_symbols` 재사용).
- **BarCache 변경**: `peek_price`/`peek_bars`(캐시 전용, fetch 없음, miss→None) 추가. 기존
  `get_price`/`get_bars`(fetch-on-miss)는 prefetch 워커와 BriefAssembler(턴 스레드)가 사용.
- **detect_wakes 변경**: `_abnormal_events`/`_watch_events`/`_watch_met`가 `peek_*` 사용.
  - `_abnormal_events`(critic R1→R3 정정): **2단계** — `detect_abnormal`을 **먼저** 호출(price만 None이어도
    volume 분기로 신호 가능, abnormal.py:52-55), 신호 있으면 기존대로 latch/fire. 신호 없을 때만
    **`price is not None and bars is not None and len(bars)>0`이면 `discard`(re-arm)**, 아니면 `continue`
    (데이터 부족=판정 보류, latch 유지). `and`(R1)는 bars-only-miss를 re-arm, `or`(R2)는 volume-abnormal
    누락 — 둘 다 틀려 detect-first 2단계로 확정. FD-B 코드 스케치 참조.
  - `_watch_met`(critic LOW): peek None → 미평가(False지만 `mark_fired`는 fire 시점에만 → 트리거 미소비,
    다음 tick 재평가). 갭은 "watch 추가 직후 첫 prefetch 주기" + **prefetch가 특정 종목 bars에 지속
    실패(상폐/심볼오류/레이트리밋)하면 close_* watch가 그 구간 미발화**(R3 LOW). 후자는 실해 작아 문서화만;
    필요 시 peek_bars가 stale-but-present 폴백(bars.py:67)을 노출하는 옵션 고려.
- **price_ttl**: 더 이상 detect 경로에서 의미 없음(peek는 TTL 무시). prefetch가 5s마다 갱신하므로
  사실상 가격 신선도=5s. (Q-B1=B 채택; TTL 상향(A안)은 불필요해 미적용.)

## C. 런처 self-heal 설계 — ⚠️ critic R1+R3 반영, **최종 (advance-only 폐기)**
**정정 1 (R1)**: active+wedge 감지는 기존 `healthWait`가 이미 한다(daemon.ts:296-309; 사용자가 본
메시지가 이것). 새 작업은 **patience 연장 + 자동 restart**뿐.
**정정 2 (R3)**: round-1의 advance-only(fresh 게이트 제거)는 **폐기**. `healthWait`는 `HEALTH_POLL_MS`
(1s)마다 폴링하고 publish 직후 45s간 fresh=true라 **느린-정상 데몬도 publish 직후를 잡아 healthy**
판정한다(오살 없음 — round-1 전제가 틀림). fresh 제거는 "죽어가며 마지막 publish 1회" 레이스로 죽은
데몬을 attach할 위험만 들인다(daemon.ts:291-294). → **`fresh && advanced` 유지, 기존 `healthWait`를
그대로 재사용하고 timeout만 조절. 새 헬퍼 불필요.**

- 신규 상수 `WEDGE_PATIENCE_MS = 180_000`(3분). 기존 `HEALTHWAIT_TIMEOUT_MS=60_000` 재사용.
- 흐름 (기존 `ensureRunning` daemon.ts:240-275 구조에 최소 삽입):
  1. `isFreshNow()` → fresh면 attach(+probeAdvance). (변경 없음)
  2. not-fresh → `ensureInstalled` → `state()`:
     - `failed` → 기존 진단 throw.
     - **`active`** (wedge 후보) → **별도 헬퍼로 빼 early-return**(critic R3: 그냥 끼우면 restart 후
       공통 :267 `healthWait`가 또 돌아 이중 healthWait). ① `healthWait(WEDGE_PATIENCE_MS=180s)` healthy면
       return(busy/slow). ② unhealthy → **restart 직전 `isFreshNow()` 레이스 가드**(active 경로 신규;
       :258은 inactive에만) → wedge면 `systemctl --user restart` 1회 → ③ `healthWait(RESTART_HEALTH_MS=180s)`
       → healthy return / unhealthy fail-closed throw.
     - `active` 아님 → 기존 start → :267 `healthWait(60s)` (변경 없음).
  - 즉 active 경로를 :267 공통 healthWait로 **흐르지 않게**(early-return) 분리. inactive(정상 start)는
    60s 유지(회귀 0). 기존 테스트(`launcher.test.ts:198,218`)의 fresh+advance 시맨틱 보존.
- **restart 후 대기 `RESTART_HEALTH_MS=180s`(R3 정정)**: healthy는 다음 advance에서 나며(`pub>initial`),
  restart 직후 낡은 snapshot이 `initial`로 찍히고 새 데몬 첫 publish가 그보다 커질 때 성립. LLM 리서치
  턴은 turn_lock이라 bus(publish)를 안 막아 보통 ~5–10s지만, 안전 마진으로 60s 대신 180s(다운사이드=
  실패 보고 지연뿐). round-2의 "60s 충분" 근거 문장은 폐기.
- **안전(SECURITY-15)**: restart=`systemctl --user restart`(이중기동 불가). 실패 시 거짓 attach 금지.
  진단 메시지에 토큰/키 미포함(SECURITY-03).
- **오판 방지(FR-C4)**: published_at은 turn_lock과 별개로 5s advance → 정상 긴 턴은 patience 내 advance
  관측 → restart 안 됨. **잔여 리스크(대형 bus 배치 점유)**는 현 ~5–10종목 ≪3분 안전; 유니버스 확장 시
  patience 상향 재검토. **죽어가는 데몬 마지막-publish 레이스**는 기존 코드도 감수하던 것(daemon.ts:234,
  콘솔 disconnect 배너 S6가 잡음) — 본 설계가 새로 들이지 않음.

## 보안 컴플라이언스 요약
- SECURITY-03 (예정 compliant): 신규 로그 시크릿 미포함.
- SECURITY-11 (예정 compliant): 타임아웃+try/except+self-heal 다층, 이중기동 금지.
- SECURITY-15 (예정 compliant): 외부 호출 에러 처리, self-heal fail-closed, 세션 헬퍼 graceful no-op.
- 그 외 N/A(웹/DB/IaC/인증/배포·의존성 신규 없음).

## Infrastructure Design: SKIP (로컬 systemd 데몬).
