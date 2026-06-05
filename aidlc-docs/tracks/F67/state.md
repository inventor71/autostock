# Track F67 — 자가학습 스택 code-review 핫픽스

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F67
- **Title**: 자가학습 스택(F62+F65+F64) code-review 핫픽스 — efficacy ts AttributeError + stamp 인덱스 + 캐시 원자성 + regime 매칭 + 프롬프트 조립 일반화
- **Type**: feature (hotfix)
- **Status**: merged → main 4f2b1b2 (2026-06-06)  <!-- /ai-dlc-merge: rebased onto fff3d9e(F66 머지 반영, 충돌 없음 — F66=settings only), verify green (977 passed), --no-ff merged -->
- **Branch**: feat/F67 @ 8d01713
- **Worktree**: .claude/worktrees/F67
- **Submodule branch**: — (monorepo; parent-repo Python only)
- **Base commit**: f17d595 (post-F64-merge main)
- **Start Date**: 2026-06-06

## Extension Configuration
- **Security Baseline**: Enabled — N/A 위주 (내부 에이전트 로직 버그픽스, 시크릿/IaC/auth 무관). SECURITY-09(fail-safe) 관련: collector ts 파싱이 fail-safe하게 None 반환하던 것이 사실상 항상 실패였던 것을 정정.
- **Property-Based Testing**: 기존 PBT 유지(efficacy/recall). 신규 회귀 테스트는 example-based.

## Scope
방금 머지된 자가학습 스택(F62 efficacy + F65 recall + F64 self-rewrite)에 대한 max-effort `/code-review`(7 angle)에서 발견된 6건 수정. 관련: [[f64-f65-self-learning-design]].

**명확한 버그 (3)**:
- **#1** `collector._parse_exec_ts`: `datetime.timezone.utc` → AttributeError(datetime은 클래스). `except`가 삼켜서 모든 naive 타임스탬프가 None 반환 → F62 효능 귀속 거의 전부 손실. `timezone.utc`로 수정 + 회귀 테스트.
- **#2** `orchestrator._run`: `before = count_decisions()`(원시 줄 수)인데 `_stamp_new`는 `read_decisions()`(파싱, malformed skip) 슬라이스 → malformed 줄 시 신규 결정 누락. `len(read_decisions())`로 수정(다른 경로와 일관).
- **#5** `orchestrator`: `_efficacy_cache_day: date | None`이 미import `date` 참조(F821, `__future__ annotations`로만 생존). 모듈 레벨 `from datetime import date` 추가.

**판단 항목 (UAQ 결정, 3)**:
- **#3** efficacy 캐시 스레드 레이스 → **원자적 기록만(락 없음)**: 두 캐시 필드를 단일 `(day, dict)` 튜플로 합쳐 cross-thread swap이 torn read 불가. 중복 recompute는 수용.
- **#4** regime relevance → **전체 텍스트 + substring**: `build_fingerprint`가 비주석 줄 전부 join(첫 줄만 아님), `_relevance`는 `\b..\b` 정규식 대신 substring 매칭(sector와 일관, 'risk-off' 등 하이픈 태그 처리). 미사용 `re` import 제거 + 회귀 테스트.
- **#6/#9** 프롬프트 조립 → **단일 레이어 일반화**: `_assemble_turn(core, lessons=)` 추가로 4개 guidance 콜사이트 통합(새 턴 타입이 preamble 빠뜨릴 위험 제거) + sequential `synthesis_prompt`에 signal_brief 추가(parallel-only였던 F61 비대칭 해소).

**미수정 (follow-up 후보, latent/cleanup)**:
- #7 rollback-then-rewrite 순서(orchestrator:657) — `_rewrite_fn=None`이라 inert. rewrite_fn 배선 시 처리.
- #8 collect_outcomes EOD 2회 호출(efficiency) — efficacy 캐시를 outcomes까지 확장하면 해소.
- #10 `is_meaningful`/`persists` 프로덕션 콜러 0(dead) + min_effect=0.0 무력 게이트 — recall/self_rewrite에 배선 또는 제거(임계 단일화) 판단 필요.

## Merge Risk Notes
- **공유 파일**: `src/agent/orchestrator.py`, `src/agent/recall.py`, `src/agent/prompts.py`, `src/agent/quality/collector.py` — 자가학습 스택(F62/F65/F64)이 방금 머지된 직후라 동일 영역. 다른 active 트랙 중 `src/agent/` 건드리는 트랙(F66 health-check 등)과 rebase 충돌 가능.
- **API/시그니처 변경**: `synthesis_prompt(total_rounds, signal_brief=None)` 인자 추가(하위호환), `orchestrator._assemble_turn` 신규 헬퍼.
- **알려진 동시 변경**: F66(`src/agent/` health-check 픽스) — 머지 순서에 따라 rebase 필요.

## Stage Progress
- [x] Workspace Detection — reused (brownfield)
- [x] Requirements Analysis — minimal (code-review 발견 6건, 명확 3 + UAQ 3)
- [x] User Stories — SKIP (내부 버그픽스)
- [x] Workflow Planning — SKIP (단일 핫픽스, lean track)
- [x] Construction — 6건 수정 (커밋 8d01713)
- [x] Build & Test — **977 passed** (975 + 회귀 3 - 옛 테스트 1 갱신). py_compile 클린.
- **Status**: merge-awaiting → `/ai-dlc-merge`
