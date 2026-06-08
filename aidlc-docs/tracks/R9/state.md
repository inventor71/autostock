# Track R9 — `config.py` ↔ `settings.py` 용어 통일

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R9
- **Title**: 패키지 로컬 설정 모듈 명칭을 `settings.py`로 통일 (config/settings 혼용 해소)
- **Type**: refactor
- **Status**: backlog  <!-- not started; pick up via /ai-dlc-refactor R9 -->
- **Branch**: refactor/R9 (TBD)
- **Worktree**: .claude/worktrees/R9 (TBD)
- **Submodule branch**: — (Python only)
- **Base commit**: 2a4e02f (survey point; rebase when picked up)
- **Start Date**: TBD

## Extension Configuration
- **Security Baseline**: N/A (설정 모듈 개명만; 키/시크릿 처리 불변).
- **Property-Based Testing**: N/A.

## Scope
같은 개념("패키지별 설정 dataclass")이 두 이름으로 갈린다(점검 #3, HIGH):
- `config`: `src/benchmark/config.py`, `src/early_session/config.py`
- `settings`: `src/agent/intraday/settings.py`, `src/signals/settings.py`, `src/surge/settings.py`

거기에 최상위 `config/` 패키지 + `config.config.get_settings()`(전역 설정)까지 겹쳐 "config가 셋".
**패키지 로컬은 전부 `settings.py`로 통일**하고, 전역 설정(`config/`)과의 역할 구분을
이름·docstring으로 명확화한다. **순수 T1, 동작 보존**.

- `benchmark/config.py` → `benchmark/settings.py`; `early_session/config.py` → `early_session/settings.py`.
- 최상위 `config/` 와 `config.config.get_settings()` 는 유지(전역 = "config", 로컬 = "settings"로 의미 고정).

**함수/심볼 네이밍 전수검사 (요구사항)**: 개명 모듈의 클래스/심볼명도 정합
(예: `BenchmarkConfig` vs `*Settings` 혼용 시 한쪽으로 — Stage 3에서 규칙 확정). 모든 import·호출·
`monkeypatch` 타깃을 `rg`로 전수 조사 후 일괄 변경. 테스트 green 유지, shim 없이 호출부 직접 갱신.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/benchmark/*`, `src/early_session/*` + 각 import 호출부. 비교적 격리.
- **API/시그니처 변경**: 모듈명 2건 개명 + (선택) 설정 클래스명 통일.
- **알려진 동시 변경 / 권장 순서**: early_session/benchmark은 다른 R-트랙과 거의 안 겹침 →
  **가장 먼저(R9) 실행 권장**. R13(tests)이 동일 테스트 import를 건드릴 수 있음(R13을 뒤로).

## Stage Progress (skill: ai-dlc-refactor)
- [ ] Stage 1 — Baseline (현 config/settings 사용처 인벤토리; 기존 테스트 green)
- [ ] Stage 2 — Tier ledger (all-T1)
- [ ] Stage 3 — Redesign (명명 규칙: 로컬=settings / 전역=config; 클래스명 통일 결정)
- [ ] Stage 4 — Implementation (개명 + 전수 호출부 갱신)
- [ ] Build & Test
