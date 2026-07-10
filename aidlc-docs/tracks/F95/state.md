# Track F95 — Symbol 클릭 → 주요 정보 floating panel

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F95
- **Title**: Symbol 클릭 → 주요 정보 floating panel
- **Type**: feature
- **Status**: merge-awaiting  <!-- active → merge-awaiting (set when Build & Test passes) → merged (by /ai-dlc-merge) -->
- **Branch**: feat/F95
- **Worktree**: .claude/worktrees/F95
- **Submodule branch**: — (monorepo; operator-console/cli 변경 예상)
- **Base commit**: 4f3fcbf
- **Start Date**: 2026-07-06T15:47:16Z

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | No | Requirements Analysis |
| Property-Based Testing | No | Requirements Analysis |

> 사용자 opt-in "No preference" → 둘 다 미적용. 읽기 전용 TUI UI 기능(외부 입력 없음, 알고리즘 로직 최소)이라 두 확장 모두 해당 없음/미적용이 합당.

## Scope
autostock의 UI에서 종목(symbol/ticker)을 클릭하면 그 종목의 주요 정보를
floating panel(오버레이)로 띄운다. 대상 surface·정보 항목·상호작용은
Requirements Analysis 단계에서 확정. 관련: [[opentui-zorder-hittest]] (TUI hit-test),
[[timeline-midnight-crossing-regions]].

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. `/ai-dlc-merge`가 큐 구성·충돌 해결 시 참조.

- **공유 파일 (주의)**: `src/agent/steering/runtime.py`(hot — __init__ + 신규 refresh_quotes/_recent_quote_symbols, import 추가), `src/agent/steering/channel.py`(quotes_file + publish_quotes), `src/trading/modes/agent.py`(스케줄 잡 1줄), `operator-console/.../routes/session/index.tsx`(InterventionOverlay 배선 1줄), `tui-trading/src/index.ts`(export). 신규 파일: `src/agent/steering/quotes.py`, `tui-trading/src/hooks/use-quote.ts`, `tests/test_steering_quotes.py`, `symbol-overlay.tsx`/`intervention-overlay.tsx` 수정.
- **API/시그니처 변경**: 없음(순수 추가). `InterventionOverlayProps.onSymbolClick?` optional 추가(비파괴). `SteeringChannel.publish_quotes` 신규.
- **알려진 동시 변경**: F73(viz-shell, do-not-enqueue), F84(모바일 차트), F33(paused) — 모두 이 트랙과 파일 무겹침. steering runtime.py는 자주 바뀌는 파일이라 rebase 시 __init__/메서드 추가 위치만 확인.

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — Standard (feasibility 조사 2건 반영, UI/UX 명확화 2라운드 + 정정)
- [x] User Stories — SKIP (단일 운영자, 시나리오 requirements.md에 명료)
- [x] Workflow Planning — EXECUTE 8 stages, SKIP User Stories + Infrastructure Design
- [x] Application Design — EXECUTE (데몬 warm-cache 프로듀서 ↔ TUI 리더 경계, quotes.json 계약)
- [x] Units Generation — EXECUTE (U1 Python warm-cache 프로듀서 / U2 TS TUI 패널·리더; 계약우선·병렬)
- [x] Construction (per-unit Code Generation)
  - [x] U1 데몬 per-instance REST warm-cache 프로듀서 — quotes.py(QuoteBook+candidates) + channel.publish_quotes + runtime.refresh_quotes/_recent_quote_symbols + agent.py @2s. 테스트 8/8, 회귀 17/17.
  - [x] U2 TUI 패널 + warm-cache 리더 + intervention 클릭화 — use-quote.ts + SymbolOverlay Quote 섹션(always) + intervention 심볼 클릭 + index.tsx 배선 + index.ts export. typecheck 19/19.
- [x] Build & Test — typecheck 19/19, unit 8/8 + integration, regression 146/146, live data-plane smoke PASS. build-and-test-summary.md + post-merge-guide.md 작성.

## Functional Design 결정 (확정)
- **quotes.json 스키마**: `{"quotes": {"<SYM>": {"price": <float>, "ts": "<ISO>"}|{"error": "<reason>", "ts": "<ISO>"}}, "updated": "<ISO>", "provider": "<name>"}`. v1은 price+ts만(등락/전일종가는 후속 — 데이터 비용 절감).
- **갱신 주기**: `QUOTE_SECS=2`(agent.py 하드코딩, order_prices=12 패턴). TTL=10s. provider 레이트리밋 시 fail-honest 스킵+백오프.
- **candidate**: held ∪ open_orders ∪ 최근 decisions/interventions distinct 심볼, 상한 30(우선순위 held>orders>recent).
- **시세 소스**: `executor.data_provider`(계정무관). 헤드라인=라이브 시세(as-of), position 줄=broker 마킹가(별도, 상이 가능 — 정직 분리 표기).
- **캐시-미스 온디맨드**: v1 미채택(클릭 대상=turn/intervention 심볼→대개 candidate). 미스 시 "조회 중" 후 다음 refresh 편입.
- **TUI 폴링**: useQuote ~1500ms(use-monitor-data 패턴).

## 시세 반응성 결정 (사용자 확정) — ADR requirements §9
- 클릭 즉시 표시(디스크 warm 값 읽기) + **~1-2s 신선도(per-instance REST 워밍캐시)**.
- 데몬: candidate 집합(보유∪주문∪최근 turn/decision/intervention)을 ~1-2s 배치 REST(`fetch_latest_prices`)로 갱신 → 자기 steering warm-cache(원자적, `_price_book` 패턴).
- **멀티 인스턴스 문제 원천 배제**: 지속 websocket 없음 → Alpaca 1-연결 한도·공유볼륨·사이드카 불필요. broker_api 포함 동일(시세 provider는 브로커와 분리).
- 폐기: per-instance 스트리밍+fail-honest 강등(사용자 지적). 보류: 공유 스트리밍 사이드카(초이하 필요 시 후속).
- [ ] Build & Test
