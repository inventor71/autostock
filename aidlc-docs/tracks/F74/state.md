# Track F74 — Prompt Eval & Regression Framework (promptfoo 기반)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F74
- **Title**: Prompt Eval & Regression Framework — 합성 시나리오로 agent turn 행동을 자동 채점하는 promptfoo 기반 회귀 게이트
- **Type**: feature
- **Status**: active
- **Branch**: feat/F74
- **Worktree**: .claude/worktrees/F74
- **Submodule branch**: — (monorepo; operator-console/cli 미접촉 예정)
- **Base commit**: 76ff7b6
- **Start Date**: 2026-06-12T00:30:00Z

## Extension Configuration
- **Security Baseline**: Disabled (사용자 opt-out 2026-06-12 — 내부 개발 도구; 시크릿 취급은 기존 repo 관행 준수)
- **Property-Based Testing**: Enabled — Partial (순수 함수·직렬화 round-trip만; framework: hypothesis, venv 기존 존재)

## Scope
실전 교훈(lessons.md)을 동결된 합성 시나리오로 만들고, 프롬프트/guidance 변경 시 agent의
실제 행동(decisions.jsonl 산출물)을 자동 채점하는 회귀 평가 파이프라인. promptfoo를
matrix runner + llm-rubric(Claude judge) + diff UI 레이어로 사용.

사전 설계 확정 사항 (인셉션 전 대화 + /critic 라운드에서 결정, 트랙 audit.md 참조):
1. **Fixture 아키텍처**: env-var 분기가 아닌 **단일 주입 팩토리** — 기존 seam
   (`_provider`/`_broker`/`_signal_collector`)에 더해 **주입 인자 없던 8개 명령**
   (fundamentals/short_data/news/earnings/insider/analyst_upgrades/institutional/macro)에
   ticker_factory/news_provider seam 신설. 13개 tool 표면의 fixture 계약 명세.
   **보유 상태 fixture 1순위, 브로커는 기존 SimulatedBroker 재사용 우선** (신규 FakeBroker
   지양). (근거: critic 1R HIGH-1 + 2R MEDIUM-1/2)
2. **세션 격리**: provider는 `one_shot=True` + (시나리오,버전,런)별 임시 workspace.
   `.sessions/` fixture 제외. (근거: 날짜-키 세션 resume 충돌 — critic HIGH-3)
3. **가드레일 채점 = 실제 executor 재사용**: 산출 decisions를 진짜 DecisionExecutor +
   FakeBroker에 통과시켜 ExecutionOutcome.status로 판정. 룰 재구현 금지. (critic MEDIUM-5)
4. **Tier-1 행동 채점 = non-blocking 시그널** (사용자 결정): CI 하드 게이트는 진짜 결정적인
   것(스키마/추출 무결성)만. flake rate 데이터 축적 후 게이트 승격 재판단.
5. **WebSearch/WebFetch 허용** (사용자 결정): 프로덕션 동일 조건 평가. 귀결: 시나리오는
   가능한 한 실제 과거 사건 리플레이(WWDC, AVGO 캐스케이드)로 작성, 루브릭은 웹발 노이즈
   감안해 "행동의 방향"을 채점.
6. **matrix 축 = F64 guidance 버전**(workspace/guidance/history.json)이 1차.
   prompts.py/CLAUDE.md 변경은 git 브랜치 vs main 비교로 별도 커버. 두 축 혼합 금지.
7. **기대행동 = (action, side) 허용 집합** — 예: "선제 청산" = SELL(sell_pct=1.0) |
   ADJUST_STOP(타이트닝) | (short이면) BUY_TO_COVER.
8. **v2로 명시 이연**: F64 test-then-adopt 게이트(self_rewrite.py:171 즉시 swap을
   candidate 상태 + adopt(gate_fn)로 리팩터링 필요), 웹 스텁 옵션, morning 3-round 시나리오,
   red-team 본격화.

v1 스코프: tools 팩토리 리팩터링 + FakeBroker fixture → promptfoo Python provider(one_shot,
격리 workspace) → wake/intraday/EOD 시나리오 10–15개(실사건 리플레이 우선) → Tier-1
non-blocking 리포트 + Tier-2 llm-rubric nightly.

비용 구조: 피평가 agent = claude -p(구독 OAuth), judge = ANTHROPIC_API_KEY(종량, nightly).

관련 메모리: [[f61-market-signals]] (Tier-2 harness 선례), [[f64-f65-self-learning-design]],
[[codekb-ci-headless]] (claude -p headless 패턴).

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. `/ai-dlc-merge`가 큐 구성·충돌 해결 시 참조.

- **공유 파일 (주의)**: `src/agent/tools/__main__.py` (팩토리 리팩터링 — F72 스크리닝 로깅
  트랙이 tools를 건드릴 가능성), `src/agent/session.py` (provider가 사용, 수정 최소화)
- **API/시그니처 변경**: TBD
- **알려진 동시 변경**: F71(모바일), F72(스크리닝 로깅), F73(viz-shell), R8 — 현재 인지된
  활성 트랙. `evals/` 신규 디렉터리는 충돌 없음.

## Stage Progress
- [x] Workspace Detection — brownfield, CodeKB 존재(ec2875c 기준, read-only 소비), RE 스킵
- [x] Requirements Analysis — standard, `inception/requirements/requirements.md` (critic 2R 반영, 2026-06-12 승인)
- [x] User Stories — **skip** (내부 개발 도구; 승인 시 미선택으로 확정)
- [x] Workflow Planning — `inception/plans/execution-plan.md` (2026-06-12 승인)
- [x] Application Design — `inception/application-design/application-design.md` C1~C8 + D1~D6 (승인 대기)
- [ ] Units Generation — execute (U1 tools 팩토리 → U2 harness → U3 시나리오)
- [x] Construction — U1 `95e9b5e`(tools fixture/record 인터셉트) → U2 `2f0de7c`(harness:
      sandbox/orchestrator 경유/Tier-1 채점/promptfoo 글루) → U3 `6de01eb`(추출기+코퍼스 11종).
      FD 정제 2건 기록: R1(디스패치 인터셉트 — market.py에 주입 파라미터 기존재 확인),
      R2(equity.jsonl 일자별 스냅샷 → 보유/계좌 자동 추출 승격)
- [x] Build and Test — **전체 1200 passed 토큰-0** (신규 127 포함), promptfoo 0.121.15 설치
      검증, 격리/동작보존/guidance 주입 증명. `construction/build-and-test/` +
      `post-merge-guide.md`. **실 LLM 스모크는 사용자 확인 대기** (구독 토큰 비용)
