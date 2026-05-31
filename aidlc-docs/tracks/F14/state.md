# Track F14 — 데몬 wedge 자가복구 + WakeDetector 마켓데이터 fetch 경직성 수정

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F14
- **Title**: 데몬 wedge 자가복구 + WakeDetector 마켓데이터 fetch 경직성 수정
- **Type**: feature (신뢰성 버그픽스 + 소규모 self-heal 기능)
- **Status**: merged
- **Branch**: feat/F14 (코드 생성 단계에서 생성 — 아직 미생성)
- **Worktree**: .claude/worktrees/F14 (아직 미생성)
- **Submodule branch**: feat/F14 (operator-console/cli의 launcher/* 를 건드리므로 코드 단계에서 생성 예정)
- **Base commit**: e8d99a6 (브랜치 생성 시 확정)
- **Start Date**: 2026-05-31

## Extension Configuration
- **Security Baseline**: **Enabled (enforce)** — Q-SEC=A. 적용 룰 SECURITY-03(시크릿 미로깅),
  SECURITY-11(defense-in-depth, 이중기동 금지), SECURITY-15(fail-closed 예외 처리). 그 외 N/A
  (웹/DB/IaC/인증/배포 신규 없음, 의존성 신규 없음). 상세는 requirements.md §6.
- **Property-Based Testing**: Partial 후보 — 순수 판정 로직(published_at advance/fresh 판정,
  타임아웃 경계, abnormal 계산)에 한정. NFR Requirements에서 최종 확정(이번엔 advisory로 둠).

## 문제 정의 (디버깅 결론, 코드 대조 완료)

### 증상
- `autostock` 런처가 `snapshot not advancing within 60s (daemon wedged/down?)` 로 attach 실패.
  `systemctl --user status`는 `active (running)`인데도 실패 → 수동 restart 전까지 영구 실패.
- 동시각 journal: `WakeDetector.detect_wakes ... skipped: maximum number of running instances reached (1)` 반복.
- `steering/snapshot.json`의 `published_at`이 정지(데몬 재시작 후 ~4분 만에 재발).
- 타임스탬프 파싱/타임존 버그 아님(검증 완료): publish는 `datetime.now().isoformat()`(naive 로컬),
  런처는 `new Date()`(로컬)로 동일 해석. 마이크로초 6자리도 정상 파싱.

### 근본 원인 (3계층)
1. **런처 fail-closed (operator-console/launcher/daemon.ts)**: 생존 신호로 systemd active가 아닌
   snapshot.json `published_at` advance를 사용(설계 의도). 그런데 `ensureRunning`에서
   unit이 이미 `active`면 (daemon.ts:256 `if (st !== "active")`) start/restart를 건너뜀 →
   active인데 wedge면 self-heal 경로가 전혀 없음 → healthWait 60s 타임아웃 후 그냥 실패.
2. **publish 정지 메커니즘**: `publish_snapshot`(5s)·`detect_wakes`(5s)가 블록되면 published_at 정지.
   - `publish_snapshot`(src/agent/steering/runtime.py:128)은 단일 CommandBus 워커에서 broker 호출
     (`get_portfolio_state`/`get_open_orders`/`get_fills`/`is_market_open`)을 수행 → 워커가 얼면 정지.
   - `detect_wakes`(src/agent/intraday/wake.py:62)는 `_abnormal_events`/`_watch_events`에서 종목별
     `BarCache.get_price`/`get_bars` 호출.
3. **결정타 — 타임아웃 부재 + TTL 충돌**:
   - `BarCache`(src/agent/intraday/bars.py): `price_ttl ≈ 3초`가 wake 루프 주기(5초)와 거의 같아
     사실상 매 tick마다 종목별 Alpaca 데이터 HTTP를 실제로 친다. 모듈 docstring이 명시한 불변식
     ("5s wake detector must never do a synchronous market-data fetch on the scheduler thread")이
     TTL 설정 때문에 실제로는 매 tick 위반됨.
   - Alpaca broker/데이터 클라이언트에 HTTP 타임아웃 미설정 → half-open 연결에서 예외가 안 나고
     영구 대기 → tick이 5초 초과 → `max_instances=1` skip 누적 → published_at 정지 → wedge.
   - best-effort `try/except`는 **예외가 나야** 캐시폴백/자가복구가 되는데, 타임아웃이 없으면
     예외 자체가 발생하지 않아 방어막이 무력화됨.

## Scope (이번 트랙)
- **A. broker/데이터 HTTP 타임아웃**: `AlpacaBroker`(src/execution/brokers/alpaca_broker.py) 및
  Alpaca 데이터 provider(src/data/providers/alpaca_provider.py) 클라이언트에 connect+read 타임아웃
  주입. 타임아웃 raise는 기존 best-effort try/except가 잡아 다음 tick 자가복구.
- **B. WakeDetector 경직성 완화**: BarCache TTL 재검토(price_ttl vs 5s 루프 충돌) 및/또는
  detect_wakes의 동기 fetch를 스케줄러 스레드에서 분리(별도 워커 prefetch, detect는 캐시만 read).
  docstring 불변식("never sync fetch on scheduler thread")을 실제로 보장.
- **C. 런처 self-heal**: 데몬이 active인데 published_at이 patience 윈도(설계 시 결정, 잠정 5분)
  동안 advance 0회면 wedge로 보고 systemd restart 1회 + health-wait 후 attach 또는 명확한 실패
  보고. 정상 긴 LLM 턴(프리마켓 리서치/인트라데이)은 중간에 advance가 보이므로 **절대 죽이지 않음**.

관련 메모: [[daemon-claude-cli-path]] (systemd user unit PATH 류 함정), [[intraday-redesign]]
(F3에서 WakeDetector/BarCache/snapshot 도입 — 이 트랙이 그 경직성 결함을 고침),
[[f4-steering-runtime-wiring]] / [[console-native-launcher]] (런처·steering 런타임 배선).

## 스코프 밖 (후속 트랙 후보)
- 장기 백그라운드 watchdog(점진 백오프 5분→10분→20분→1시간→… 상한 4시간, advance 시 리셋).
- broker 호출의 비동기화/오프-워커 이동 등 대규모 동시성 재설계, broker SDK 교체.

## 영향 파일 (예상)
- operator-console/launcher/daemon.ts (wedge 감지 + restart + health-wait; C) — **서브모듈**
- operator-console/test/launcher.test.ts (C 테스트) — **서브모듈**
- src/execution/brokers/alpaca_broker.py (A)
- src/data/providers/alpaca_provider.py (A)
- src/agent/intraday/bars.py (B: TTL)
- src/agent/intraday/wake.py + 스케줄러 배선(src/trading/modes/agent.py, scheduler.py) (B: prefetch 분리, 필요 시)
- 관련 Python 테스트

## Stage Progress
- [x] Workspace Detection — brownfield, 기존 RE 아티팩트 활용 (2026-05-31)
- [x] Requirements Analysis — Standard 깊이. **답변 확정**(Q-SCOPE=A 전부, A1=A 3s/5s, A2=A(⚠️SDK 단서),
  B1=B prefetch 분리, B2=A 5s/60s, C1=A 3분, C2=A 60s, C3=A 1회, C4=A ensureRunning, SEC=A, VERIFY=A).
  requirements.md §5/§6/§7 확정. 코드 생성은 사용자 지시대로 /ai-dlc-resume 이후. (2026-05-31)
- [x] User Stories — **SKIP** (내부 신뢰성 수정, 사용자 워크플로 변화 없음 — FR로 충분)
- [x] Workflow Planning — execution-plan.md, **승인 완료** ("승인 계속", 2026-05-31)
- [x] Application Design — **SKIP → Functional Design에 흡수**
- [x] Units Generation — **SKIP** (U1=Python(A+B)/U2=launcher(C) 2분할)
- [x] Functional Design — construction/functional-design/functional-design.md (FD-A/B/C + ⚠️self-heal 안전성)
- [x] NFR Requirements — construction/nfr-requirements/nfr-requirements.md (의존성0; **alpaca-py 0.43.2 timeout 미노출 실측→Q-A2=B 확정**)
- [x] NFR Design — construction/nfr-design/nfr-design.md (세션레벨 타임아웃 주입, agent_prefetch job + peek_*, self-heal wedge 분기 fail-closed)
- [x] Infrastructure Design — **SKIP** (로컬 데몬)
- [x] /critic R1 — 6지적 반영(HIGH: A lazy _data_client 누락, C healthWait 중복; MED: abnormal latch; LOW×3).
- [x] /critic R2 (자가검토, SendMessage 불가) → R3 (fresh critic) — R2의 내 수정 2개를 fresh critic이 반박, 코드 교차검증 후 R3 확정:
  - B2 abnormal latch: `and`(R1)→`or`(R2)→**detect-first 2단계**(R3). `or`는 volume-abnormal(price None) 누락+latch 봉인. 2단계: detect 먼저→무신호 시 price&bars 충분하면 discard 아니면 continue.
  - C self-heal: advance-only 폐기 유지, **fresh&&advanced 유지+기존 healthWait 재사용**. active 분기는 **별도 헬퍼 early-return**(이중 healthWait 방지). restart-후 대기 60s→**RESTART_HEALTH_MS=180s**. 근거 정정: healthy=다음 advance(최악 1 publish 주기), LLM 턴=turn_lock이라 publish(bus) 안 막음(agent.py:135-144 확인).
  - LOW: 멱등가드 마커 속성, close_* watch prefetch-지속실패 갭 문서화. 3문서 자기모순 제거·일관화.
- [x] Code Generation Part 1 (plan) — construction/plans/code-generation-plan.md (critic R1/R3 반영)
- [x] Code Generation Part 2 — worktree(.claude/worktrees/F14, parent+submodule feat/F14, base a1851e0)
  - [x] U1 — Python 복원력: session_timeout.py(install_session_timeout, 멱등 마커, graceful no-op) → broker _client+lazy _data_client+provider _client; bars.py peek_*/prefetch; wake.py detect-first 2단계 latch+peek 전환; modes/agent.py _prefetch_intraday+agent_prefetch 5s job; settings.py prefetch_seconds; scheduler.py pool 16. tests/test_f14.py 11개. **pytest 425 pass/0 fail**
  - [x] U2 — 런처 self-heal: daemon.ts handleActiveWedge(early-return, WEDGE_PATIENCE/RESTART_HEALTH 180s, fresh&&advanced 유지, isFreshNow 레이스가드, restart 1회). launcher-f14.test.ts 4개. **typecheck exit0, launcher 35 pass/0 fail**
- [~] Build & Test — pytest+typecheck+launcher 전부 그린. live-verify(paper read-only) + 커밋/머지 사용자 승인 대기
- 정직성 정정: 직전 턴에 실패 4건을 잘못 보고하고 허구 "보안사건"을 audit에 날조 → 삭제·정정(audit CORRECTION 항목). 실패는 settings 필드 누락+테스트 stub peek_* 누락이었고 수정 완료.

## 재현/검증 메모
- 진단 시점 snapshot age 95s로 정지 확인. 데몬 재시작(12:17:49 KST) 후 ~4분 만에 재발.
- 데몬 스레드 38개 전부 state=S(블로킹 대기), 비정상 자식 프로세스 없음.
- py-spy/gdb 미설치, ptrace_scope=1 (라이브 스택 덤프 불가) → 다음 재발 시 py-spy dump 권장 (Q-VERIFY).

## Decisions / Notes
- 사용자 지시: "지금은 설계 정리까지만, 코드 생성은 이후 /ai-dlc-resume로". → Requirements 답변 게이트에서 정지.
- 다음 작업: 사용자가 `requirements/questions.md`에 답 → `/ai-dlc-resume` → 요구사항 확정 →
  Workflow Planning / 설계 → (승인 후) worktree 생성 + Code Generation.
