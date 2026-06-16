# Track F73 — viz-shell: 읽기 전용 생성형 대시보드 사이드카 (vibeOS 패턴 방향 A)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F73
- **Title**: viz-shell — 읽기 전용 생성형 대시보드 사이드카 (vibeOS 패턴 방향 A)
- **Type**: feature
- **Status**: active
- **Branch**: `vibeshell` (사용자 지정 — `feat/F73` 컨벤션 대신 명시 요청)
- **Worktree**: .claude/worktrees/F73 (2026-06-13 생성)
- **Submodule branch**: — (monorepo; operator-console/cli 미접촉 예정)
- **Base commit**: 8fa4e4b (2026-06-16 rebase — 원분기 5a00442에서 main 54커밋 위로 재배치;
  트랙 생성 시점 main = 76ff7b6). 데이터 표면 drift 없음, build/test/16라우터 스모크 green.
- **Start Date**: 2026-06-12T00:07:10Z

## Merge Policy (사용자 지정 — 표준과 다름, 글로벌 룰 명시적 override)
> **장기 브랜치.** 사용자 지시: "vibeshell이라는 다른 브랜치에서 진행하는 방식으로 나중에
> 충분히 안정되었을 때 머지". Build & Test green이어도 **자동으로 `merge-awaiting`으로
> 전환하지 않는다** — 사용자가 명시적으로 "안정됐다, 머지하자"고 선언할 때까지 `active` 유지.
> `/ai-dlc-merge` 큐에 조기 진입 금지.
>
> ⚠️ 이 정책은 CLAUDE.md Build-and-Test Step 5의 MANDATORY "green→merge-awaiting" 룰을
> **이 트랙에 한해 의도적으로 override**한다(사용자 결정, audit 기록). 미래 세션 주의:
> Build & Test green 후에도 Status를 `merge-awaiting`으로 바꾸지 말 것. 루트 Registry
> 행에도 `do-not-enqueue` 표기됨.
>
> **주기적 rebase**: main의 유의미한 머지(특히 `workspace/`·`steering/` 데이터 표면 변화)
> 마다 vibeshell을 최신 main 위로 rebase해 디버전스 비용을 상한한다 (critic 라운드 반영).

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | Yes (전체 blocking; 스테이지별 N/A 판정 허용) | Requirements Analysis (2026-06-12, UAQ) |
| Property-Based Testing | Partial (순수 함수/직렬화 라운드트립만 — jsonl 파서, zod 스키마 변환) | Requirements Analysis (2026-06-12, UAQ) |

## Scope
vibeOS(caffeinum/vibeOS) 패턴의 "방향 A"를 autostock에 이식: 레포에 읽기 전용 생성형
대시보드 웹 사이드카 `viz-shell/`을 추가한다.

1. **Next.js 사이드카 앱** — `steering/snapshot`, `logs/`(journal/turn/equity/trades),
   lessons, signals 산출물을 **읽기 전용 tRPC 라우터**로 노출. Python 데몬 **무변경**
   (파일 직접 읽기, 순수 additive).
2. **채팅 패널 → Claude Code SDK `query()`** — 앱 자신의 `generated/` 디렉토리만 편집
   허용. vibeOS와 달리 `bypassPermissions` 금지, terminal류 라우터 없음.
3. **Next.js dev 서버 HMR**이 생성된 뷰를 즉시 반영 (반응성 계층).
4. **쓰기/스티어링 경로는 기존 operator-console에 그대로** — viz-shell은 순수 읽기 전용.

참고 분석: vibeOS 백엔드 코드 조사 완료(2026-06-11 대화) — 핵심 = 영구 dev 모드 +
인프로세스 Claude Code SDK가 자기 소스 편집 + HMR이 렌더링 엔진. 관련 메모리:
[[opentui-zorder-hittest]] (기존 TUI는 별개 표면), [[worktree-gate-hook]].

## Merge Risk Notes
> 트랙이 merge 후보로 전환 시 작성. (장기 브랜치 — Merge Policy 섹션 참조)

- **공유 파일 (주의)**: 거의 없음 예상 — 신규 `viz-shell/` 디렉토리가 대부분.
  루트 `.gitignore`, `README.md`, `scripts/` 보조 정도.
- **API/시그니처 변경**: 없음 (Python 데몬 무변경 원칙).
- **알려진 동시 변경 (critic 라운드 갱신, 2026-06-12)**: F71·F72는 **이미 main에 머지됨**
  (F71→fdfc041, F72→7b4b409, 둘 다 2026-06-12; R8도 머지 — equity 생산자는
  `src/agent/logs/equity.py`). worktree 분기는 트랙 생성 시점 기록(76ff7b6)이 아니라
  **그 시점의 최신 main**에서 한다. F72가 추가한 `workspace/screening/` 표면은 후속
  확장 시 기존 계약 재사용.

## Stage Progress

### 🔵 INCEPTION PHASE
- [x] Workspace Detection — brownfield, CodeKB 존재(stale: ec2875c vs HEAD 76ff7b6, 근사 컨텍스트로 사용)
- [x] Reverse Engineering — SKIP (CodeKB baseline; 신규 디렉토리 + 파일 읽기 전용 소비)
- [x] Requirements Analysis — standard, 2026-06-12 승인 (`inception/requirements/requirements.md`)
- [x] User Stories — SKIP (운영자=개발자 본인 1명)
- [x] Workflow Planning — `inception/plans/execution-plan.md` 승인 (2026-06-12, critic 반영판)
- [x] Application Design — 승인 (2026-06-13) — `inception/application-design/` 5문서, UAQ 3결정(단일 세션/거부+표시/도구 요약)
- [ ] Units Generation — SKIP (단일 유닛)

### 🟢 CONSTRUCTION PHASE (단일 유닛: viz-shell)
- [x] Functional Design — 승인 (2026-06-13) — 4문서 (`construction/viz-shell/functional-design/`); 추가 지침: UI 깔끔/무버그/reformable
- [ ] NFR Requirements — SKIP (requirements NFR-1~7로 확정)
- [ ] NFR Design — SKIP (Application Design에 통합)
- [ ] Infrastructure Design — SKIP (로컬 dev 서버 단일 프로세스)
- [x] Code Generation — 승인(2026-06-13). vibeshell 109f631 + code-review 8건 e9c959a. 테스트 108/108 + 라이브 스모크
- [x] Build & Test — ✅ GREEN (tsc 클린 / vitest 108 / next build OK / 경계 테스트 / 라이브 IT). **장기 브랜치 — `active` 유지(merge-awaiting 전환 안 함)**. Post-Merge Guide 작성

### 🟢 후속: 지표 확장 (F83 철회 후 순서 정상화 — 2026-06-14)
> F83(공유 카탈로그)을 critic 검증 후 철회하고, 원래 목표(viz-shell 지표 부족 해소)를
> vibeshell에서 직접. Tier 로드맵은 대화 정리분(Tier 0 공짜 → 1 핵심 → 2 분석 → 3 리서치).
- [x] **Tier 0** (2026-06-14) — snapshot 미사용 필드 노출. 스키마 확장(open_orders/recent_fills/
  round_trip/run_state) + 위젯 4종(RunStateBadge/OpenOrdersTable/RoundTripCard/RecentFills),
  라우터 추가 0. 테스트 110 통과 + 라이브 스모크(API 5 orders/8 fills, 위젯 렌더). 미체결
  브래킷/OCO 가시성 확보(최대 격차 해소).
- [x] **Tier 1** (2026-06-14) — decisions/turns/trades. paths 3 + schemas(Decision/Turn/Trade) +
  router 3 query(tailJsonl, limit 1..500) + 위젯 2종(RecentDecisions: action/confidence + reason
  펼침, TradesTable: 청산 라운드트립) + view-contract에 신규 훅 4개 안내. turns는 라우터만(생성뷰용).
  테스트 118 통과(+7 라우터), Tier1 코드 tsc 클린, 라이브 스모크(decisions 3/turns 2/trades 5 실데이터, 위젯 렌더).
- [x] **Tier 2** (2026-06-14) — quality/health/watchlist/regime. paths 4 + schemas(Quality/Health
  중첩 loose + MarkdownDoc) + router 4 query(quality=최신 날짜파일 선택, health=atomic, watchlist/
  regime=stat-stable md). **시드 탭 배열화** — `seed-tabs.tsx`(Overview/Analysis), TabBar/page 일반화
  (생성뷰 자동활성·hidden-views 로직 보존). AnalysisTab = QualityPanel + HealthPanel + MarkdownDoc×2
  (거대 md는 펼침-온디맨드 fetch). Overview 비대화 해소. 테스트 124 통과(+6), tsc 클린, 라이브
  스모크(quality 최신 22 outcomes/health ERROR 5dim/watchlist 102KB/시드탭 2개).
- [x] **Tier 3** (2026-06-15) — screening/sentiment/surge/daily/lessons. paths 5 + schemas(Scan/
  Verdict/Sentiment) + router 6 query(**날짜 파라미터** {date?} optional — 최신 기본 + 임의 날짜,
  목록 대조로 경로주입 차단). 신규 시드 탭 **Research**(seed-tabs 3엔트리화). 정형 위젯 2종
  (ScreeningFunnel: scan→verdicts 퍼널, SentimentPanel: bull/bear 막대) + MarkdownDoc 5종 일반화
  (surge/daily/lessons 추가). 테스트 132 통과(+8), tsc 클린, 라이브 스모크(screening 최신+특정날짜
  06-14 조회, sentiment 500, surge/daily/lessons md, 시드탭 3개).

### 🟣 vibeOS 철학 점검 + 보정 (2026-06-15)
> 사용자 요청: "지금까지 코드가 vibeOS 철학 살리는지 체크". 점검 결과 + 반영:
- **충실**: tRPC 서비스 계층(query 16개로 확장) = vibeOS "시스템 서비스 계층" 정신, HMR 자동
  레지스트리·ErrorBoundary 탭 격리·채팅 생성 경로(사용자 실제 뷰 2개 생성) = 반응성/격리 핵심.
- **보정 1 (빌드 격리 갭)**: 생성뷰(unrealized-pnl)가 tsc/next build를 깨뜨리던 문제 → `tsconfig`
  exclude `src/generated` (런타임 ErrorBoundary가 유일 안전망이라는 vibeOS 철학과 빌드 게이트를
  일관화). 이제 깨진 생성뷰가 빌드를 막지 않음. tsc 트릭(mv) 불필요.
- **보정 2 (생성 모범 빈약)**: _example이 snapshot 하나뿐 → `_example-research.tsx` 추가
  (decisions jsonl-tail + 집계 + recharts 패턴 시연) + view-contract에 16훅 + 날짜조회 안내 +
  "시드 탭에 국한 말고 무엇이든 표면화하라" 명시. 서비스 계층의 풍부함을 생성 경로가 따라가게.
- **잔여 긴장(기록)**: 시드 위젯 20개+로 정적 대시보드화 경향 — 즉시 가치 있으나 vibeOS는
  최소 시드+생성 위임이 정신. 향후 Tier는 시드 절제 + 생성 모범 우선 고려. → **아래 보정 3에서 해소.**

### 🟣 시드 위젯 절제 (중도) — vibeOS 본질 강화 (2026-06-16)
> 사용자 결정: "중도로 가자". 상시 운영 핵심(돈/리스크)은 검증된 시드로 안정성 유지,
> 탐색적 데이터는 생성으로 위임.
- **Overview 시드 유지** — 계좌/포지션/미체결 주문/run-state/체결/결정/트레이드 (항상 정확해야
  하는 운영 상태 = 안정성. 생성 뷰의 조용한 오집계 위험을 피함).
- **Analysis + Research 탭 → Explore 탭 하나로 통합**. 정형 위젯 6종(QualityPanel/HealthPanel/
  ScreeningFunnel/SentimentPanel + analysis/research-tab) **삭제**. 대신:
  - **프리셋 칩 갤러리**(`preset-gallery.tsx`, 6칩) — 칩=하드코딩 위젯이 아니라 **생성 프롬프트**.
    클릭 → ChatPanel `presetPrompt` 주입 → 자동 전송 → 에이전트가 `generated/`에 뷰 생성.
  - 경량 health 배지(overall만, 상시) + 마크다운 문서 뷰어 5종(watchlist/regime/surge/daily/
    lessons, 열람용 — 생성 아님).
- **배선**: page `presetPrompt` 상태 + `onPreset`(칩→채팅), ChatPanel `presetPrompt`/`onPresetConsumed`
  (single-flight 존중). SeedTab.Component 타입을 `{onPreset?}` 수용으로 넓힘.
- 효과: 시드 정형 위젯 6 제거, 탐색은 생성 경로로. "풍부한 라우터(16) → 생성으로 활용"의 vibeOS
  본질 강화. 라우터는 전부 유지(생성 연료).
- 검증: vitest **135 통과**(+3 PresetGallery, -6 삭제 위젯 테스트 없었음), tsc 클린, 라이브
  스모크(시드탭 Overview+Explore, 프리셋류 프롬프트 → 에이전트 generated/ 생성 확인).

#### critic 반영 (2026-06-16, "vibeOS 본질 유지하며 critic")
> 코드 교차검증 후 반영. LOW 3건은 critic이 safe 확인(무조치).
- **[HIGH] 프리셋 자동전송 stuck** — inFlight 중 칩 클릭 시 sendMessage·onPresetConsumed 둘 다
  skip + deps [presetPrompt]만이라 턴 종료 후 재실행 안 됨 → 프롬프트 영영 손실. **수정: 자동전송
  → textarea 프리필(편집 가능, 사용자가 명시 전송)으로 전환.** 자동전송 effect 제거 → stuck 경로
  구조적 소멸 + 사용자 agency 회복(vibeOS 본질). ChatPanel `prefill={text,nonce}`, page nonce++.
- **[MEDIUM] 같은 칩 재클릭 value-equality drop** — prefill `nonce`로 monotonic 트리거(같은 텍스트도
  재발화). 동시 해결.
- **[설계/#3 vibeOS 본질]** critic: "프리셋이 파일명/라이브러리/버킷까지 과지정 = 생성 의상 입은
  큐레이션, 자동전송은 agency 박탈". **반영: ① 프리필(편집 후 전송) ② 프롬프트 under-specify(의도
  + tRPC 훅만, 파일명/recharts/버킷 제거 — 시각설계는 에이전트 판단) ③ 자유입력을 헤드라인으로,
  칩은 "막막할 때 예시".** 진짜 생성 표면=자유 채팅임을 UI가 반영. 테스트도 "src/generated/·
  recharts 미포함" 검증으로 갱신.
- Overview 시드(계좌/포지션/주문) 유지 = critic도 타당 인정(trust-critical·money-adjacent → LLM
  전사 오류 위험, 비결정 생성에 맡기지 않음).

> ⚠️ **발견(F73 갭, Tier 0 중)**: 사용자가 채팅으로 만든 생성 뷰(`src/generated/
> unrealized-pnl-by-symbol.tsx`)에 타입 에러가 있어 `tsc --noEmit`·`next build`를 깨뜨림.
> 런타임은 ErrorBoundary로 격리되나 **빌드/타입체크 게이트는 generated/를 포함해 오염**.
> dev(HMR) 운영엔 무해. 처리 방안(생성뷰를 tsc/build 스코프에서 제외 등)은 별도 결정 대기.

## Current Status
- **Lifecycle Phase**: CONSTRUCTION 완료 + 후속 지표 확장 진행 중
- **Current Stage**: Tier 0 완료 (지표 확장 후속) — vibeshell, 미커밋→커밋 예정
- **Next Stage**: Tier 1(decisions/turns/trades) 또는 사용자 지시. 장기 브랜치 유지
  (merge-awaiting 전환 안 함). main 유의미 머지마다 vibeshell rebase 권장.
