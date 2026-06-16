# Track F85 — Aggressiveness knob (단일 다이얼 → 프롬프트 + 리스크)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F85
- **Title**: Aggressiveness knob — 한 개의 운영자 다이얼로 매매 공격성 조절 (프롬프트 + 리스크 게이트)
- **Type**: feature
- **Status**: merged → main 207b8be (2026-06-16)
- **Branch**: feat/F85
- **Worktree**: .claude/worktrees/F85
- **Submodule branch**: — (monorepo)
- **Base commit**: <branch 생성 시 기록>
- **Start Date**: 2026-06-14

## Extension Configuration
- **Security Baseline**: **Enabled** — 적용 룰: 노브 입력 검증(field_validator fail-safe), 리스크
  파라미터 경계 검증, preset overlay가 안전 게이트(shorting_enabled 등) 미오염. N/A: 네트워크/인증/시크릿
  (이 트랙은 외부 노출면 없음 — 로컬 config 다이얼).
- **Property-Based Testing**: **Enabled** — 모드: 레벨→파라미터 매핑 순수함수의 단조성/경계 속성 +
  maturity 게이트(today−ts vs horizon) 경계. 프레임워크: hypothesis (Python).

## Scope
한 개의 "aggressiveness" 운영자 노브를 도입해, **프롬프트 엔지니어링(에이전트가 무엇을·얼마나
적극적으로 찾고 거래할지)**과 **결정론적 리스크 게이트(사이징/스톱/포지션수/할트)**를 한 다이얼로
동시에 움직인다. **핵심: aggressiveness = 단타(짧은 horizon)/장투(긴 horizon)의 "학습 루프 시간축"
다이얼.** 관련: [[llm-trader-redesign]] [[risk-execution-redesign]] [[f64-f65-self-learning-design]]
[[f80-storage-format-rationale]].

**확정 스코프 (UAQ + critic 반영, 2026-06-14):**
- **A** 프롬프트 발굴 포커스 + 리스크 게이트 프리셋(overlay-only, named-field allowlist).
- **C1** `Decision`에 horizon/level 스탬핑(F62 재사용; restamp 손상라인 거부 caveat).
- **C3-full** 채점 horizon·lookback 레벨 파생(일봉) + **maturity 게이트**(today−ts<horizon→efficacy 제외)
  + **성숙 시점 1회 확정채점 grading-state 영속**. quality/ 내부 신규, F74와 중복 없음.
- **C4** recall **recency 가중치만** 레벨화(`orchestrator.py:321` weights=). idle_days 은퇴는 후속.
- **intraday churn 문구** 레벨화(scheduler 간격 불변).
- **F74 재사용** `evals/tests.yaml` 레벨별 시나리오 + guidance_label 행(새 채점기 금지).
- 전 결정-생성 프롬프트 빌더 전수 배선(critic: shorting_enabled는 7중 2개만 배선된 부분 패턴).
- fail-safe: `field_validator(mode=before)` 비멤버→balanced(critic: Literal은 크래시).

**후속 스택:** C2-full(intraday price_path 단타 채점), C4 idle_days 은퇴 영속화, F74 nightly/CI 자동화,
scheduler 틱 간격 레벨화.
값=이산 레벨(conservative|balanced|aggressive, 기본 balanced), 적용=settings.yaml+재시작.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/agent/prompts.py`, `src/agent/orchestrator.py`, `main.py`,
  `config/config.py`, `config/settings.yaml`, `src/risk/manager.py`/`position_sizer.py`,
  `src/agent/quality/collector.py`+`efficacy.py`, `src/agent/learning/recall.py`,
  `src/agent/journal.py`(Decision 필드 추가), `evals/tests.yaml`. 다수 핫패스 — 동시 트랙과 충돌 가능.
- **API/시그니처 변경**: 프롬프트 빌더들에 `aggressiveness` 인자 추가, `Decision`에 horizon/level 필드
  추가, `RiskManager` 구성에 preset overlay, `collect_outcomes`/efficacy에 maturity 게이트.
- **알려진 동시 변경**: F76(thesis/journal), F81(shorting_enabled 방향게이트), F83(산출물 카탈로그) —
  journal/decisions·shorting·prompts 인접. 머지 전 재확인.

## Stage Progress
- [x] Workspace Detection — brownfield, 기존 활성 트랙 다수(F73/F76/F79/F81/F83/F84). 신규 요청.
- [x] Requirements Analysis — 조사·철학심화·critic·기존자산조사·스코프 UAQ + **승인 완료** (depth: standard)
- [x] User Stories — **skip**: 신규 사용자 페르소나/워크플로 없음(운영자 단일 config 다이얼). 요구사항이 행동을 충분히 규정.
- [x] Workflow Planning — `inception/plans/workflow-planning.md`
- [x] Application Design (minimal) — 컴포넌트 경계 = functional-design §0
- [x] Functional Design — `construction/functional-design/functional-design.md` (+critic 3R, 승인)
- [x] Units Generation — **skip**: 단일 응집 단위(분해 불필요)
- [x] NFR (minimal) — functional-design §9 (Security Baseline/Property-Based로 흡수)
- [x] Construction (per-unit Code Generation) — `code-generation-plan.md` 전 단계 완료 (worktree feat/F85)
- [x] Build & Test — `pytest -q`: **1373 passed** (+ F85 27건); 사전존재 3건(F77 sentiment_sweep, F85 무관)
  제외. compile/wiring smoke green. `post-merge-guide.md` 작성.
