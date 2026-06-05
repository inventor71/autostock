# Track F62 — 귀속/효능 기반 (Attribution & Efficacy Base, U0)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F62
- **Title**: 귀속/효능 기반 — "레슨/프롬프트버전 → 결정 → 결과" 링크 + 효능 스코어 (자가학습 에픽 U0)
- **Type**: feature
- **Status**: merged → main 9342691 (2026-06-06)  <!-- /ai-dlc-merge: rebased onto 30e3609 (F30 머지 반영, 충돌 없음), verify green (941 passed), --no-ff merged. 스택 base — F65/F64가 이 위에 순차 머지. -->
- **Branch**: feat/F62 @ f54d018
- **Worktree**: .claude/worktrees/F62
- **Submodule branch**: — (monorepo; parent-repo Python only)
- **Base commit**: 43b26d7 (main HEAD at worktree 생성; 구 e8b112b에서 갱신)
- **Start Date**: 2026-06-05T09:48:53Z

## 에픽 위치 (자가학습 3트랙)
- **F62 (이 트랙)** — 공유 귀속/효능 기반 (U0). **먼저 머지.**
- **F65** — 하이브리드 회상 (F62 위 분기). 효능 스코어를 랭킹에 소비.
- **F64** — 헌장 경계 자가재작성 (F65 위 분기). 효능 스코어를 진화/롤백 판정에 소비.
- 의존성/머지 순서: **F62 → F65 → F64.** 설계 전모: 메모리 [[f64-f65-self-learning-design]].

## Scope
F24 결정품질 메트릭은 **측정만 하고 행동으로 피드백되지 않으며**, `LessonRecord.times_applied`
(`src/agent/journal.py:43`)는 **선언만 되고 한 번도 증가하지 않는 죽은 필드**다. 두 후속 트랙이
공통으로 필요로 하는 빠진 1차 조각 — **"레슨/프롬프트버전 → 결정 → 결과" 귀속 링크**와 그 위의
**효능 스코어** — 를 만든다.

1. **Decision 스키마 확장** (`src/agent/journal.py`, decisions.jsonl):
   `lessons_cited: list[str]` (이 결정의 근거 레슨 id) + `prompt_version: str` (결정 시점 가이던스
   프롬프트 버전). 둘 다 **추가-only, 기본값으로 하위호환** (기존 decisions.jsonl 라인 무손상 파싱).
2. **LessonRecord 확장**: `regime: str` + `sector: str | None` 태그 (F65 회상 키), `times_applied`
   **부활** — 레슨이 인용될 때 증가.
3. **`src/agent/efficacy.py` 신규** (순수함수): F24 collector
   (`src/agent/quality/collector.py:259`)의 결정→체결→결과 매칭을 재사용해
   `lesson_id`별 `{applied_n, win_rate, avg_excess}` + `prompt_version`별 동일 집계 산출.
   **LLM 호출 없음, 결정론, 단위테스트 가능.**
4. **인라인 통계 가드** (경량, F72 대체): `min_sample` / 효과크기 / 지속성 임계를 판정하는 순수
   함수. "통계적으로 의미있는 신호인가"를 F65 랭킹 신뢰·F64 진화 판정이 공유.

### Critic Review (2026-06-05) — 반영
격리 critic 적대검토 결과 3 HIGH 코드확인·반영:
- **HIGH#1**: `append_decision`은 死코드 — 결정은 LLM이 직접 씀. `lessons_cited`=LLM emit(CLAUDE.md
  스키마+프롬프트), `prompt_version`=Python 사후 스탬프(restamp). `times_applied`=저장 말고 파생.
- **HIGH#2**: `DecisionOutcome`에 excess 없음 + collector가 BUY/SELL만 처리 → **collector를 확장**
  (숏 포함 + `excess` 부착). 사용자 결정: 숏까지 확장.
- 상세: functional-design business-logic-model §2.1/§3, requirements FR-2c/FR-3.3.

관련 메모리: [[f64-f65-self-learning-design]], [[llm-trader-redesign]], [[risk-execution-redesign]]

## Out of Scope (후속 트랙)
- 회상 로직(태그 필터/LLM 재랭크) → **F65**
- 프롬프트 자가재작성/헌장/컴플라이언스/롤백 → **F64**
- 정식 통계 유의성(Bootstrap CI/permutation) → 미정 F72 (본 트랙은 경량 인라인 가드만)
- `times_applied`를 **소비**하는 랭킹 → F65 (본 트랙은 **증가**만 배선)

## Extension Configuration
- **Security Baseline**: Enabled — SECURITY-03 (no secrets in logs). 대부분 N/A (순수 데이터
  레이어, 신규 거래 경로/외부 호출 없음).
- **Property-Based Testing**: Partial (Hypothesis) — efficacy 집계·통계 가드가 순수 함수 →
  직렬화 round-trip / 단조성 / 빈입력·경계 PBT.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/agent/journal.py` (Decision/LessonRecord 스키마),
  `src/agent/quality/collector.py` (재사용 import). decisions.jsonl 스키마 변경은 golden
  contract / TUI 인접 타입과 동기화 필요할 수 있음 — 확인 항목.
- **API/시그니처 변경**: `Decision`에 `lessons_cited`/`prompt_version` 추가(기본값 → 하위호환);
  `LessonRecord`에 `regime`/`sector` 추가. **추가-only**, 기존 필드 불변.
- **알려진 동시 변경**: **F61(시그널 강화)**가 `src/agent/prompts.py`/`orchestrator.py`/`tools/market.py`
  를 건드림 → 본 트랙은 `journal.py`/`quality/`/신규 `efficacy.py` 중심이라 **파일 겹침 거의 없음**.
  단 `orchestrator.py`에서 레슨 인용 배선이 필요하면 함수 레벨 분리 주의.

## Stage Progress
- [x] Workspace Detection — reused (brownfield)
- [x] Requirements Analysis — standard (`inception/requirements/requirements.md`)
- [x] User Stories — SKIP (내부 데이터 인프라, 사용자 페르소나 변화 없음)
- [x] Workflow Planning — single unit (`inception/plans/execution-plan.md`)
- [x] Application Design — folded into Functional Design (신규 컴포넌트 1: efficacy)
- [x] Units Generation — single unit (unit-attribution)
- [x] Functional Design — `construction/unit-attribution/functional-design/business-logic-model.md`
- [x] Construction (Code Generation) — COMPLETE 2026-06-05 (commit f54d018)
  - [x] schema 확장 (Decision/LessonRecord) + 하위호환 검증
  - [x] efficacy.py (순수함수) + 통계 가드 + PBT
  - [x] times_applied = read시 파생(applied_counts) + prompt_version restamp (critic HIGH#1 반영)
  - [x] collector 숏 확장 + excess 부착 (critic HIGH#2 반영); lesson 도구 regime/sector
- [x] Build & Test — PASS (824 green, 0 new deps). `construction/build-and-test/build-and-test-summary.md`
