# Track F30 — KIS OpenAPI 브로커 확장

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F30
- **Title**: KIS OpenAPI 브로커 확장 — 한국투자증권 API를 통한 한국주식 페이퍼트레이딩
- **Type**: feature
- **Status**: active
- **Branch**: feat/F30
- **Worktree**: `.claude/worktrees/F30` (생성됨 2026-06-03 — F35 머지로 차단 해소)
- **Submodule branch**: — (F35가 submodule 자체를 제거 → monorepo, 해당 없음)
- **Base commit**: 2253029 (post-F35 monorepo main; 구 base b4fa955에서 갱신)
- **Start Date**: 2026-06-01

## ✅ Worktree 차단 해소 (F35 머지 완료)
- **F35(submodule→monorepo 통합)는 2026-06-03 main `2253029`로 머지 완료.** worktree 차단 해소.
- F30 worktree를 post-F35 main에서 재생성: `.claude/worktrees/F30` (branch `feat/F30`, Python `--py`).
- **앱 코드(src/ KIS 브로커)는 worktree에서만** 생성한다(worktree gate). 설계 문서·state·audit는
  status/registry 라이브 유지를 위해 main 루트 체크아웃에서 계속 편집.
- 남은 단계: Functional Design → NFR Requirements (문서) → Code Generation (worktree) → Build & Test.

## Scope
autostock에 한국투자증권(KIS) OpenAPI를 **한국주식 전용** 브로커로 추가하는 **KIS 단독 PoC**:
- 기존 BaseBroker 인터페이스로 KIS OpenAPI 연동
- KOSPI 200 + KOSDAQ 150 종목 페이퍼트레이딩 (Q8=A)
- KIS OpenAPI로 시세 데이터 통합 (Q9=A)
- 공식 SDK git dependency + 래핑 (Q10=A)
- KIS OpenAPI REST 기반 (Linux 호환)
- 실전/모의 환경 분리 (KIS_PAPER_* 환경변수)
- DecisionExecutor: bracket 검증 우회, HOLD/ADJUST_STOP KIS no-op
- TradingScheduler: KST 타임존 파라미터 추가
- 멀티브로커 동시 운영(Alpaca US + KIS KR)은 **F33으로 분리**

Related memories: [[llm-trader-redesign]], [[risk-execution-redesign]], [[worktree-live-verification]]

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard
- [ ] User Stories — skip (내부 인프라 확장, 사용자 페르소나 변화 없음)
- [x] Workflow Planning — standard
- [x] Application Design — execute (KisBroker + KisDataProvider 컴포넌트 설계) + **델타(2026-06-03)**: Universe Provider unit 추가 (BaseUniverseProvider / KRUniverseProvider / USUniverseProvider + 테마 config). 아래 ## Application Design 델타 참조.
- [~] Units Generation — **재스코프(2026-06-03)**: 당초 단일 컴포넌트로 스킵했으나, Q6 답변으로 **universe 동적화가 별도 unit으로 추가** → F30은 이제 **2-unit**: (U1) kis-broker, (U2) universe-provider
- [x] Functional Design — execute **완료(2026-06-03, 승인)**. U1: 주문유형 매핑(MARKET→01/LIMIT→00/STOP→cndt_pric), 호가단위 반올림(Q2=A nearest), 정수수량(Q3=A), emulated OCO 폴링(Q1=A 5초 job 합승, Q4=A 진입 동기확인), 토큰 lazy 갱신(Q5=A), close=시장가(Q8=A), standalone 폴링=보유+open만(Q7=A). U2: 동적 base+테마 overlay. 주의: KIS 국내주식 시장가 지원 확인됨 — MARKET→LIMIT 변환 불필요
- [x] NFR Requirements — execute **완료(2026-06-03, 승인)**. rate limiting(실전~15/모의2 token-bucket+backoff), 토큰 lazy, HTTP connect3/read5, KST, universe 캐시1일+fallback, Security 매핑, PBT Partial, tech stack(기존 dep 재사용, KIS SDK git 핀)
- [~] Construction — per-unit (U1 kis-broker, U2 universe-provider)
  - [x] Code Generation — Part 1 승인, Part 2 **완료**(6 커밋, 613 passed). Critic 7건 반영.
    - **Foundation slice 완료+검증(2026-06-03, 51 passed)**: SDK 핀(python-kis==2.1.6, import `pykis`), `BaseBroker.halt_reference_symbol`+`cancel_settle_wait`, `kis_pricing.round_to_tick`(출력-tier 재snap)+`floor_qty`+PBT, executor(halt broker-aware+WARNING/protected STOP-leg/cancel-wait broker-tunable), scheduler timezone 파라미터화. → critic MED-3(executor측)/MED-5/LOW-6/LOW-7 해소.
    - **KIS 검증 완료(2026-06-03)**: 모의 실호출 — 인증 OK, **스탑지정가(22) 모의 미지원 확정**(40970000), pykis 모의 시세 불가(EGW02004). 검증사실 [[kis-api-facts]]. 결정: 런타임 모의 도메인 raw REST, 환경분기(모의=폴링 SL/실전=거래소 스탑).
    - **KisPaperBroker 완료+검증(2026-06-03)**: `kis_rest.py`(토큰 lazy/1분제한/throttle) + `kis_broker.py`(`KisBroker(ABC)` 공통 + `KisPaperBroker` 구체 + 실전 `_arm_stop` abstract 훅). submit(market/limit/OCO·BRACKET TP=거래소지정가/SL=폴링), 잔고→positions/portfolio, open_orders, cancel/close, OcoGroup 저널, reconcile, is_market_open(KST). **단위 17 passed + 라이브 read-only(auth/balance: 모의 시드 5천만 확인)**. 주문 placement 검증은 모의 장시간(09:00–15:30 KST)에.
    - **U2 + 재배선 완료(2026-06-03)**: Universe providers(Base/KR/US)+config+스냅샷, **trading.symbols 전면 제거→resolve_universe(MED-4), 607 passed**. 커밋 b0024d0/aed7867/2d9897a/e078680.
    - **통합 배선 완료(2026-06-03)**: create_broker/data market-aware(broker.name=kis, client 공유) + AgentTradingMode KST 스케줄 + always-on kis_reconcile job(HIGH-1) + 5.5/5.7 테스트. 커밋 db367e9/865051e. **613 passed**.
    - **Critic 2차 하드닝 완료(2026-06-03)**: 구현 critic 검토 HIGH 4건 반영 — emulated bracket TP 지연-arm(실체결 사이징/PENDING_ENTRY 상태기계), get_order_status ccld 실구현, 모의 손절을 에이전트 stop_price로(get_protective_stops→check_stop_loss override), resolve_universe(KR) broker.client 공유(토큰충돌 제거) + throttle 스레드안전/원자적 스냅샷/tick 고정점. **619 passed**. 커밋 5b5d9cc.
    - **Follow-up ①③ 완료(2026-06-03, 커밋 3511360)**: ① KR 동적 = top-30 KOSPI+top-30 KOSDAQ(랭킹 EP 30/시장 캡, 페이징 없음), min_base 수정으로 동적 채택 + EGW00201 backoff 재시도 → **라이브 60종목(KOSPI+KOSDAQ) 확인**. ③ is_market_open KRX 공휴일(chk-holiday opnd_yn 일캐시) → 라이브 확인. **남은 것: ② 모의 장시간 주문 placement 라이브만**(평일 09:00–15:30 KST).
- [x] Build & Test — `construction/build-and-test/F30-build-and-test-summary.md` 작성. 619 passed, py_compile/import 클린, 라이브 read-only 검증 완료. follow-up: 모의 장시간 주문 placement + KR 페이징/KOSDAQ + 공휴일 캘린더. (Operations 진행 승인 대기)

## Application Design 델타 — Universe Provider unit (2026-06-03)
> Q6 답변(B + "US도 동적, 테마 extend, KRUniverseProvider 네이밍")으로 추가된 신규 unit.
> 발견: 현 US universe는 `config/settings.yaml`의 `trading.symbols` **정적 리스트**(동적 아님).
- **BaseUniverseProvider**: `get_symbols()` = 동적 base ∪ 사용자 테마(config, 이름 포함); 일 단위 캐시 + 정적 스냅샷 fallback.
- **KRUniverseProvider** (신규): base = KODEX 200(KOSPI200) + KODEX 코스닥150(KOSDAQ150) **ETF 구성종목**(KIS API). 정확 엔드포인트 = Code Gen 직전 검증.
- **USUniverseProvider** (신규, 기존 정적 동작을 동적으로 대체): base = S&P 100 구성종목 동적 조회(pandas read_html, 이미 dep) + 선택적 marketCap 랭킹(yfinance, 이미 dep) + 정적 스냅샷 fallback.
- **테마 overlay**: config에 명명 테마(예: `반도체`) 리스트(KR/US 각각), 사용자 enable/extend. 기존 curated `trading.symbols`는 테마/스냅샷으로 네이티브 이관.
- **이관 주의**: USUniverseProvider 도입은 기존 US 에이전트 실행의 traded universe를 정적→동적으로 **의도적 변경**(사용자 요청). monorepo-refactor-as-native 원칙대로 `trading.symbols`를 새 구조로 깔끔히 대체.

## Extension Configuration
- **Security Baseline**: Enabled — Full (all applicable rules). Applicable: SECURITY-03 (no secrets in logs), SECURITY-05 (input validation), SECURITY-09 (error handling, fail-safe), SECURITY-10 (dependency pinning), SECURITY-11 (secure design, defense in depth), SECURITY-12 (credential management, no hardcoded keys), SECURITY-15 (exception handling, fail-closed). N/A: SECURITY-01, SECURITY-02, SECURITY-04, SECURITY-06, SECURITY-07, SECURITY-08, SECURITY-13, SECURITY-14.
- **Property-Based Testing**: Enabled — Partial mode. Enforced: PBT-02 (round-trip), PBT-03 (invariants), PBT-07 (generator quality), PBT-08 (shrinking/reproducibility), PBT-09 (framework: Hypothesis). N/A (by partial mode): PBT-01, PBT-04, PBT-05, PBT-06, PBT-10.
