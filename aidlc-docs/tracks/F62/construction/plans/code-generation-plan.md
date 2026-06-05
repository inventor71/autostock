# Code Generation Plan — F62 unit-attribution

> **Track**: F62 · **Phase**: Code Generation (Part 1 plan) · **Date**: 2026-06-05
> 코드는 worktree `.claude/worktrees/F62`(branch feat/F62, base 43b26d7)에서만 생성.
> critic 반영본(business-logic-model 갱신) 기준.

## 구현 단계 (체크박스 = 진행 추적)
- [x] **S1 journal.py 스키마** — `Decision` += `lessons_cited: list[str]=[]`, `prompt_version: str="seed"`;
  `LessonRecord` += `regime: str=""`, `sector: str|None=None`. + `restamp_decisions(decisions)`
  (torn-safe rewrite, `steering/jsonl.atomic_write_text`) + `applied_counts(decisions)` 파생 헬퍼.
- [x] **S2 quality/models.py** — `DecisionOutcome` += `excess: float|None=None`.
- [x] **S3 quality/collector.py** — 액션 필터에 `SELL_SHORT`/`BUY_TO_COVER` 추가; outcomes 빌드 후
  `_extract_benchmark_paths`로 SPY/QQQ 경로 → 각 outcome에 **방향-인지 excess** 부착
  (진입 BUY→base, SELL_SHORT→-base; 청산/기타→None).
- [x] **S4 agent/efficacy.py (신규)** — `LessonEfficacy`/`VersionEfficacy` + `lesson_efficacy`/
  `prompt_version_efficacy`(outcome.excess group-by) + `is_meaningful`/`persists` 가드. 순수.
- [x] **S5 tools/__main__.py** — lesson `add` += `--regime`/`--sector` → LessonRecord.
- [x] **S6 templates/CLAUDE.md** — decision 스키마에 `lessons_cited` 추가 + "근거 lesson_id 적어라" 지시.
- [x] **S7 tests** — test_efficacy.py(순수+PBT), 하위호환(레거시 라인 파싱), collector 숏+excess,
  restamp round-trip, applied_counts 정합.

## 설계 메모 (critic 반영)
- **append_decision은 死코드** → S1은 거기 증가 배선 안 함. prompt_version은 Python restamp(F64에서
  배선; F62는 헬퍼만 + 기본 "seed"). lessons_cited는 LLM emit(S6 스키마/지시).
- **times_applied 미저장** → applied_counts로 read시 파생(레이스 회피). 필드는 직렬화 호환용 유지.
- **excess 방향성** → benchmark_excess는 price_path 기반 long-return. SELL_SHORT는 부호 반전.
  청산(SELL/BUY_TO_COVER)·HOLD는 excess=None (진입 결정에 효능 집중).

## 검증
worktree 메인 venv로 `pytest tests/test_efficacy.py tests/test_quality.py -q` + 전체 회귀.
py_compile/import 클린. 0 new deps.
