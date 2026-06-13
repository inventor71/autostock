# Track F78 — 이벤트-레이더 (Tier1, 인지 전용)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F78
- **Title**: 이벤트-레이더 (Tier1, 인지 전용) — IPO/매크로 촉매 인지 채널
- **Type**: feature
- **Status**: merged → main 1d3330c (2026-06-13)
- **Branch**: feat/F78
- **Worktree**: .claude/worktrees/F78
- **Submodule branch**: — (monorepo)
- **Base commit**: 01ced61 (worktree feat/F78 branched from main HEAD after F77 merge)
- **Start Date**: 2026-06-13

## Extension Configuration
- **Security Baseline**: Enabled — 신규 외부 HTTP 소스(Finnhub IPO). 적용: API 키 env-only 취급
  (`FINNHUB_API_KEY` 재사용, 로깅/예외에 키 노출 금지), 외부 응답 신뢰 경계(스키마 방어적 파싱,
  fail-honest). N/A: 인증/인가·세션·order 경로 없음(read-only 수집), 사용자 입력 없음.
- **Property-Based Testing**: Partial — pure core(IPO 선별/horizon 필터/정렬·캡)와 record
  직렬화 라운드트립에만 PBT. 수집기 I/O 경계·프롬프트 텍스트는 예제 기반.

## Scope
research 턴이 IPO·M&A·규제·매크로 같은 "아직 티커로 역인덱싱 안 된 시장 촉매"에 둔감한
문제를 **인지(perception) 채널 추가**로 해결. 두 조각:

1. **Push** — Finnhub `/calendar/ipo` 신규 소스(`sources/finnhub_earnings.py` 패턴 병렬),
   `SignalCollector.collect()`에서 earnings와 나란히 수집, `brief.py` `to_prompt_text()`에
   "Imminent IPOs / catalysts" 섹션 추가. 결정론적 push 유지(pure core), fail-honest
   (degraded_sources), TTL 캐시 공유. 기존 F61 [[f61-market-signals]] 구조 위에 얹음.
2. **Prompt** — `morning_research_prompt`의 **Regime(step 2)** 단계에 nudge:
   brief의 IPO 캘린더 + 매크로 촉매를 web research로 top-down 스캔하고 섹터/심리 영향과
   보유·universe 종목으로의 read-through를 regime.md에 기록.

**명시적 비범위**: universe 동적 승급(Tier2), day-1 IPO 직접 매수(가격 이력 없어 ATR
기반 손절 불가). MCP 리팩토링은 별도 병렬 트랙. Discovery(step 4)에는 넣지 않음(메뉴
고르기 단계 — 의미·리스크 부적합).

**보존 제약(하드)**: F74 eval fixture 시임(`AUTOSTOCK_TOOLS_FIXTURE_DIR`, CLI dispatch
가로채기)과 NFR-2 타임아웃 바운딩(session-timeout helper) 보존.

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성.

- **공유 파일 (주의)**: `src/signals/collector.py`, `src/signals/brief.py`,
  `src/signals/settings.py`, `src/agent/prompts.py` — **F77(StockTwits, F61 소스)**가 같은
  signals 계열을 건드릴 가능성 높음. 머지 시 brief 섹션/collector 와이어링 충돌 주의.
- **API/시그니처 변경**: 신규 추가 위주(새 source 모듈, 새 record 타입, brief 섹션). 기존
  시그니처 변경 최소화 목표.
- **알려진 동시 변경**: F77 (signals 소스 추가 — 인접). prompts.py는 다수 트랙이 만지므로 nudge는 additive하게.

## Stage Progress
- [x] Workspace Detection — brownfield, RE 아티팩트 존재(codekb) → reverse-eng skip
- [x] Requirements Analysis — standard (승인 2026-06-13)
- [ ] User Stories — skip 예상(내부 신호/프롬프트, 사용자 워크플로 변화 미미) — 확정 TBD
- [x] Workflow Planning — 승인 2026-06-13 (User Stories/Units/Infra skip)
- [x] Application Design — 경량 실행 (승인 2026-06-13)
- [ ] Units Generation — skip 예상(단일 단위)
- [ ] Construction (per-unit Code Generation)
  - [x] event-radar — push source + brief section + Regime nudge (commit 5722d33)
- [x] Build & Test — green (224 signals + 127 evals + 48 misc; 3 사전존재 F77 sweep 실패는 무관). 라이브 Finnhub 스모크 OK
- [x] Code Review (high) — CONFIRMED 1건 수정: FR-5 nudge가 비활성 morning_research_prompt에만 있었고 활성 multi_research_initial_prompt(multi_agent.enabled=true)에 누락 → 추가 + 회귀 가드 테스트(commit 941975c). LOW 1건(IPO 날짜창 date.today() ET 아님 — earnings와 공유 관례) 노트만.
