# Track F65 — 하이브리드 회상 (Hybrid Lesson Recall)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F65
- **Title**: 하이브리드 회상 — recency 절단 대신 상황 기반 레슨 회상 (태그 사전필터 + LLM 재랭크)
- **Type**: feature
- **Status**: merged → main 89927c7 (2026-06-06)  <!-- /ai-dlc-merge: rebased onto 9342691 (F62 머지 반영, F62 커밋 자동 cherry-skip, 충돌 없음), verify green (955 passed), --no-ff merged. F62 위 스택 — F64가 이 위에 머지. -->
- **Branch**: feat/F65 @ b80656b (feat/F62 f54d018 위 스택 — F62 미머지 상태)
- **Worktree**: .claude/worktrees/F65
- **Submodule branch**: — (monorepo; parent-repo Python only)
- **Base commit**: f54d018 (feat/F62 HEAD; F62 미머지 — 머지 전 F62/F65/F64 일괄 검수)
- **Start Date**: 2026-06-05T09:48:53Z

## 에픽 위치 (자가학습 3트랙)
- F62 — 귀속/효능 기반 (U0). **선행 머지 필수** (이 트랙이 효능 스코어를 소비).
- **F65 (이 트랙)** — 하이브리드 회상.
- F64 — 헌장 경계 자가재작성 (F65 위 분기).
- 의존성/머지 순서: **F62 → F65 → F64.** 설계 전모: 메모리 [[f64-f65-self-learning-design]].

## Scope
현재 레슨은 **recency만**으로 주입된다(`lessons[-max_n:]`, N=10; `prompts.py:198`
`_build_lesson_context`). "고VIX 갭다운 반전" 레슨이 잔잔한 추세장엔 무용한데도 관련 레슨을
밀어내고, 효능 순위가 없다. recency 절단을 **상황 기반 회상**으로 대체한다:

1. **상황 지문** (Python 조립, F3 brief 패턴): 오늘 레짐 + VIX/breadth 버킷 + 대기 액션
   카테고리 + 보유/유니버스 섹터.
2. **태그 사전필터** (순수함수): 지문과 매칭되는 레슨 후보 K' 추림 →
   `효능(F62) × recency × 관련성`으로 1차 정렬. **단위테스트 가능.**
3. **LLM 재랭크** (보유 `claude` 브레인, cheap 턴): 후보 K' 중 오늘 진짜 관련 K개 선택.
   **벡터스토어 0, 신규 dep 0.**
4. **주입**: 선택된 K개를 리서치/인트라데이 프롬프트에 주입 (`_build_lesson_context` 대체).

**Fallback (필수)**: 재랭크 턴 실패/타임아웃 시 2단계 1차 정렬 결과로 graceful 폴백.
**오염 방지**: 미검증 레슨(`applied_n < 임계`, F62 가드)은 영향 캡; 모순·낡은 레짐 레슨은
decay·은퇴(EOD 통합 스텝).

### Critic Review (2026-06-05) — 반영
- **MED**: 기존 `_build_lesson_context`(`prompts.py:198`)는 lesson_id 미출력 → 에이전트가 인용
  불가. 렌더에 **lesson_id 포함** + 인용 지시 필요(아니면 F62 lessons_cited 영구 빈값).
- **MED**: `lesson` 도구가 regime/sector 미수집 → 신규 레슨 빈 태그. **F62 FR-2.1b(생성 시 태깅)이
  선행 전제.** 미태깅 레슨은 regime 매칭에서 관련성 0(중립)로 폴백 안전.

관련 메모리: [[f64-f65-self-learning-design]], [[llm-trader-redesign]]

## Out of Scope
- 시맨틱 임베딩/벡터DB → 태그+LLM이 불충분하다고 입증될 때만 (현재 의도적 배제)
- 프롬프트 자가재작성/헌장 → F64
- 귀속 링크·효능 산출 자체 → F62 (이 트랙은 **소비**)

## Extension Configuration
- **Security Baseline**: Enabled — SECURITY-03 (no secrets in logs). 대부분 N/A.
- **Property-Based Testing**: Partial (Hypothesis) — 1·2단계(지문 조립, 태그 매칭/정렬)는 순수
  → PBT(정렬 안정성, 관련성 단조, 빈/경계). 3단계(LLM 재랭크)는 비결정 → 계약/폴백 테스트.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/agent/prompts.py` (`_build_lesson_context` 대체) — **F61(시그널
  강화)**가 같은 파일을 건드림 → 함수 레벨 분리 + F61 머지 후 rebase 주의. `orchestrator.py`
  (`_get_lessons`/주입 경로) 인접.
- **API/시그니처 변경**: `_build_lesson_context` 시그니처 변경 가능(상황 지문 인자 추가) — 내부
  함수. 신규 recall 모듈 추가.
- **알려진 동시 변경**: F62(스키마/효능 — 선행 머지), F61(prompts.py — 함수 레벨 분리).

## Stage Progress
- [x] Workspace Detection — reused (brownfield)
- [x] Requirements Analysis — standard (`inception/requirements/requirements.md`)
- [x] User Stories — SKIP (내부 에이전트 도구, 운영 패턴 확장)
- [x] Workflow Planning — single unit (`inception/plans/execution-plan.md`)
- [x] Application Design — folded into Functional Design
- [x] Units Generation — single unit (unit-recall)
- [x] Functional Design — `construction/unit-recall/functional-design/business-logic-model.md`
- [x] Construction (Code Generation) — COMPLETE 2026-06-05 (commit b80656b, feat/F62 위 스택)
  - [x] 상황 지문 조립 (순수, build_fingerprint)
  - [x] 태그 사전필터 + 효능 정렬 (순수, prefilter_and_rank)
  - [~] LLM 재랭크 + graceful fallback — **인터페이스+폴백 구현, v1 orchestrator는 OFF(순수 순위)**.
        활성화 지점 마련(rerank_fn 주입). 검수 시 활성 여부 판단.
  - [x] _build_lesson_context 교체 + 주입 배선 (lesson_id 렌더 — critic fix) + _lesson_efficacy 캐시
  - [~] decay/은퇴 — mark_retirements 순수 구현; **지속화(lessons.jsonl rewrite) follow-up**
- [x] Build & Test — PASS (838 green, 0 new deps). `construction/build-and-test/build-and-test-summary.md`
