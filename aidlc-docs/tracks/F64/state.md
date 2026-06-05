# Track F64 — 헌장 경계 자가재작성 (Constitution-Bounded Prompt Self-Rewrite)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F64
- **Title**: 헌장 경계 자가재작성 — 에이전트가 불변 헌장 안에서 자기 가이던스 프롬프트를 자동 진화
- **Type**: feature
- **Status**: merged → main a383f8d (2026-06-06)  <!-- /ai-dlc-merge: rebased onto 89927c7 (F62+F65 머지 반영, 하위 커밋 자동 cherry-skip), orchestrator.py 충돌 1건(F61 signal_brief + F64 guidance_preamble 병합), verify green (975 passed), --no-ff merged. 자가학습 스택 최상위. -->
- **Branch**: feat/F64 @ 861a259 (feat/F65 b80656b 위 스택)
- **Worktree**: .claude/worktrees/F64
- **Submodule branch**: — (monorepo; parent-repo Python only)
- **Base commit**: b80656b (feat/F65 HEAD; 스택 미머지 — F62→F65→F64 일괄 검수)
- **Start Date**: 2026-06-05T09:48:53Z

## 에픽 위치 (자가학습 3트랙)
- F62 — 귀속/효능 기반 (U0). 선행 머지.
- F65 — 하이브리드 회상. 선행 머지.
- **F64 (이 트랙)** — 헌장 경계 자가재작성. **에픽의 마지막.**
- 의존성/머지 순서: **F62 → F65 → F64.** 설계 전모: 메모리 [[f64-f65-self-learning-design]].

## Scope
에이전트가 EOD에 자기 결정품질 메트릭(F62 효능)을 보고 **자기 가이던스 프롬프트의 진화 가능
섹션을 자동 재작성**하고, **즉시 교체**한다(사용자 결정: "헌장 변경만 승인, 교체는 자동").
공격성은 사람 게이트가 아니라 **3중 안전장치**로 통제한다:

1. **🔒 불변 헌장 (Constitution)** — 레포 코드 소유(에이전트 write 불가), 모든 세대에 prepend.
   목적은 좁다: **자가개선 품질 저하 방지.** 코드가 이미 강제하는 실행-안전 규칙(자문전용/스탑/
   리스크한도/유니버스·ETB/스키마)은 **헌장에 적지 않는다.** 품질 규율 6원칙만 담는다(정직성/
   증거기반/레짐과적합방지/검증보존/점진성권장/구체성). 전문: `functional-design/constitution.md`.
   **헌장 변경만 사용자 승인 필요** (고정 체크섬 테스트로 강제) — F64의 유일한 사람 게이트.
2. **✏️ 진화 가능 가이던스** — 에이전트가 재작성하는 유일한 섹션.
3. **결정론 컴플라이언스 검증 + 자동 롤백 + 변경량 캡** — 새 세대가 라이브 가기 전 헌장 모순/
   인젝션/구조 위반을 거부; 라이브 후 N일 메트릭(F62) 악화 시 자동 parent 복귀; 세대당 diff 캡.

### Critic Review (2026-06-05) — 반영
- **HIGH#3**: 진화 가이던스의 자연스러운 집은 workspace `CLAUDE.md`인데 **에이전트가 직접 편집
  가능** → 게이트 우회 → 안전모델 붕괴. **결정(사용자): Python prepend로 이전** — CLAUDE.md에서
  진화 휴리스틱 제거, Python 저장소 단일화, 에이전트는 EOD에 "제안"만. 전 프롬프트 빌더(~10개)
  중 가이던스턴에만 주입, EOD 재귀 제외. 상세 functional-design §2.
- **MED(롤백)**: parent 1세대만 복귀 + 신규버전 cold-start N일 보류 명문화; excess는 F62 부착 의존.
- **LOW(동시변경)**: prompts.py 조립부를 F64/F65가 같은 라인에서 수정 → "함수레벨 분리"는 라인
  레벨에선 불성립. **F64는 F65의 build_lesson_context 위임 위에서 분기**(아래 Merge Risk 갱신).

관련 메모리: [[f64-f65-self-learning-design]], [[llm-trader-redesign]], [[risk-execution-redesign]]

## 핵심 불변식 (재작성 금지 경계)
`executor.py` 실행 로직, `RiskManager→Broker` 게이트, Decision 스키마, 브래킷/스탑 강제는 전부
**코드** → LLM이 못 건드린다. 자가재작성 대상은 **가이던스/시스템 프롬프트 텍스트뿐**. 즉
"더 잘 판단하라"는 진화하되, "어떻게 주문이 나가는가"는 불변. (자문/실행 분리 불변식 유지.)

## Out of Scope
- 격리 페이퍼 평가/토너먼트(F63) — 사용자가 즉시교체 택해 F63 의존 없음
- 정식 통계 유의성(F72) — 본 트랙은 F62 경량 가드 소비; F72는 후속 강화
- 효능 산출·회상 — F62/F65 (이 트랙은 소비)

## Extension Configuration
- **Security Baseline**: Enabled — SECURITY-03 (no secrets in logs), SECURITY-15 (fail-closed:
  컴플라이언스 검증 실패 시 새 세대 거부·이전 버전 유지). 실행-안전은 코드(F54/F60)가 이미 강제.
- **Property-Based Testing**: Partial (Hypothesis) — 컴플라이언스 검증(denylist/구조 바운드),
  버전 lineage, 롤백 판정이 순수 → PBT. LLM 재작성 자체는 비결정 → 계약/거부 테스트.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/agent/prompts.py` (헌장 prepend + 진화 섹션 분리) — **F61(시그널
  강화)** + **F65(회상)** 가 같은 파일을 건드림 → 함수 레벨 분리 + 머지 순서(F62→F65→F64) 준수.
  `src/strategy/llm/prompt_manager.py` (PromptVersion/lineage 재사용).
- **API/시그니처 변경**: 신규 `src/agent/constitution.py` (AGENT_CONSTITUTION 상수 + 컴플라이언스
  검증), 신규 self-rewrite 모듈, EOD 경로에 재작성 스텝 추가. prompts.py 조립 구조 변경.
- **알려진 동시 변경**: F62/F65 (선행 머지), F61 (prompts.py). **critic LOW 정정**: F64·F65·F61이
  prompts.py의 **같은 주입부**(`multi_research_initial_prompt`의 lesson_ctx 보간 `:220,231`,
  orchestrator 주입 `:404`)를 건드림 → "함수 레벨 분리"는 라인 레벨에선 불성립. F64는 F65가
  재구성한 `build_lesson_context` 위임 위에서 분기해야 함(현 인라인 형태 가정 금지).

## Stage Progress
- [x] Workspace Detection — reused (brownfield)
- [x] Requirements Analysis — comprehensive (자가재작성 = 리스크 민감; `inception/requirements/`)
- [x] User Stories — SKIP (단일 운영자; 단 헌장 승인 워크플로는 요구사항에 명시)
- [x] Workflow Planning — single unit (`inception/plans/execution-plan.md`)
- [x] Application Design — folded into Functional Design
- [x] Units Generation — single unit (unit-self-rewrite)
- [x] Functional Design — `construction/unit-self-rewrite/functional-design/`
      (business-logic-model.md + **constitution.md**)
- [x] Construction (Code Generation) — COMPLETE 2026-06-05 (commit 861a259, feat/F65 위 스택)
  - [x] constitution.py (AGENT_CONSTITUTION + 고정 체크섬 테스트)
  - [x] 2층 프롬프트 조립 (헌장 prepend + 진화 섹션, build_guidance)
  - [x] 컴플라이언스 검증 (인젝션방어/denylist/구조 바운드, 순수 fail-closed)
  - [x] 버전 저장/lineage + 즉시 교체 (self_rewrite GuidanceHistory)
  - [x] 자동 롤백 (parent 1세대 + cold-start N일 보류) + 쿨다운/최소표본 게이트
  - [x] prompt_version 스탬프(_stamp_new) + EOD 재작성 스텝 배선 (**inert: rewrite_fn=None**)
  - [~] CLAUDE.md gut / 드리프트 점검 / 저장소 cwd-밖 = follow-up (build-and-test-summary 편차 1–4)
- [x] Build & Test — PASS (858 green, 0 new deps). `construction/build-and-test/build-and-test-summary.md`
