# Track R10 — `intraday` 일원화 (`data/intraday_*` → `data/intraday/`)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R10
- **Title**: `src/data/intraday_*.py` 평면 접두 파일을 `src/data/intraday/` 서브패키지로
- **Type**: refactor
- **Status**: merge-awaiting  <!-- Build & Test green (1073 passed + 신규 -m CLI 스모크) 2026-06-11; refactor/R10에 커밋 -->
- **Branch**: refactor/R10
- **Worktree**: .claude/worktrees/R10
- **Submodule branch**: — (Python only)
- **Base commit**: 0106a8b (main HEAD at resume)
- **Start Date**: 2026-06-11

## Extension Configuration
- **Security Baseline**: N/A (데이터 수집 모듈 이동만).
- **Property-Based Testing**: N/A.

## Scope
"intraday"가 두 집에 산다(점검 #4, HIGH): 패키지형 `src/agent/intraday/` 와 평면 접두형
`src/data/intraday_{analysis,collector,features,store}.py`. 같은 단어가 다른 위치·표기로 갈려
"intraday 코드 어디?"에 답이 둘이다. **`data/` 쪽을 서브패키지로 묶어 표기 통일** — 순수 T1:

- `src/data/intraday_{analysis,collector,features,store}.py` → `src/data/intraday/{analysis,collector,features,store}.py`.
- `src/agent/intraday/`(에이전트 인트라데이 루프)와의 **역할 경계를 docstring/README로 명확화**
  (data/intraday = 데이터 수집·피처·저장, agent/intraday = 에이전트 의사결정 루프).

**함수/심볼 네이밍 전수검사 (요구사항)**: 이동 모듈의 import·호출·`monkeypatch` 타깃 전수(`rg`)
조사 후 일괄 변경. 모듈명 접두(`intraday_`)가 디렉터리로 흡수되므로 내부 함수/클래스명에서
중복 접두가 있으면 정리(예: `intraday_store.IntradayStore` → `intraday.store.Store` 검토).
테스트 green 유지, shim 없이 직접 갱신.

**외부 표면 — `-m` CLI 경로**: `intraday_collector.py:144`·`intraday_analysis.py:212`는 `argparse(prog=
"python -m src.data.intraday_collector/analysis")`로 **운영자용 CLI 진입점**을 광고한다(docstring 예시 포함).
서브패키지 이동 시 호출 경로가 `python -m src.data.intraday.collector`로 바뀐다 → silent-T1 아님.
**결정(2026-06-08): 클린 브레이크** — 새 `-m` 경로로 가고, 하위호환 shim 없이 docstring/argparse prog +
cron/runbook/스크립트의 옛 `-m src.data.intraday_collector` 참조를 동일 PR에서 전수 갱신. **post-merge-guide
필수**(옛 `-m` 경로를 쓰던 작업은 새 경로로). Stage 1에서 `rg 'intraday_collector|intraday_analysis'`로
non-src(docs/cron/scripts) 참조까지 전수.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/data/*` + 호출부(intraday 데이터 사용처) + `tests/test_intraday_*.py` 다수.
- **API/시그니처 변경**: 모듈 경로 4건 이동(시그니처 불변).
- **알려진 동시 변경 / 권장 순서**: R8과는 **파일 공유 없음**(R8은 `agent/intraday/`를 건드리지 않고
  logs/·learning/만 이동, R10은 `data/intraday`) — 다만 둘 다 "intraday"류 모듈을 개명하므로 import/테스트
  churn을 읽기 쉽게 하려고 직렬화 권장. 실질 겹침은 R13(`test_intraday_*` 재배치) → R10을 R13보다 먼저.

## Stage Progress (skill: ai-dlc-refactor)
- [x] Stage 1 — Baseline (`1-baseline.md`) — 전수 인벤토리 7건 라이브 + 오탐/제외 확정; 심볼 stutter 0
      (개명 불필요); monkeypatch 문자열 0; non-src `-m` 참조 = 과거 트랙 문서/codekb(CI 소유)뿐
- [x] Stage 2 — Tier ledger (`2-tier-ledger.md`) — 전부 T1 + `-m` 클린 브레이크(기승인), T3 게이트 없음
- [x] Stage 3 — Redesign (`3-redesign.md`) — `src/data/intraday/{features,store,collector,analysis}.py`,
      `__init__.py`=docstring만(재export shim 없음), CSV 경로 `data/intraday/` 불변
- [x] Stage 4 — Implementation — git mv ×4 + import 7곳 + argparse prog/docstring + runtime.py:563
      문자열 경로; 잔여 `intraday_*` 참조 0 (rg 확인)
- [x] post-merge-guide — 옛→새 `-m` 경로 표 + 확인 체크리스트 + 롤백 (`post-merge-guide.md`)
- [x] Build & Test — 전체 스위트 **1073 passed**; `-m src.data.intraday.{collector,analysis} --help` 스모크 OK
