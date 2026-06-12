# Track R8 — `src/agent/` 재구조화 (grab-bag 해소)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R8
- **Title**: `src/agent/` 최상위 잡탕 파일을 성격별 서브패키지로 재구조화
- **Type**: refactor
- **Status**: merge-awaiting  <!-- B&T green (1073) 2026-06-11; code on refactor/R8 -->
- **Branch**: refactor/R8
- **Worktree**: .claude/worktrees/R8
- **Submodule branch**: — (Python only)
- **Base commit**: 76ff7b6 (R9–R12 머지 후 main HEAD)
- **Start Date**: 2026-06-11

## Extension Configuration
- **Security Baseline**: Applicable — 자가학습/세션 경로가 포함되나 **이동/개명만** 한다.
  tool allowlist·권한·키 처리 면을 넓히거나 바꾸지 말 것(순수 구조 변경).
- **Property-Based Testing**: N/A (행동 보존 — 기존 테스트가 회귀 가드).

## Scope
`src/agent/` 최상위에 성격이 다른 15개 모듈이 평평하게 섞여 있어 "핵심 루프가 무엇인지"
분간이 안 된다(repo 구조 점검 #1, HIGH). 성격별 서브패키지로 묶는다 — **순수 T1, 동작 보존**:

- **로깅** → `agent/logs/`: `equity_log.py` `trades_log.py` `turn_log.py`
  (예: `agent/logs/{equity,trades,turn}.py`).
- **자가학습** → `agent/learning/`: `efficacy.py` `recall.py` `self_rewrite.py`
  `constitution.py` `review.py`.
- **stutter 제거**: `agent/agent_reports.py` → `agent/reports.py` (`agent.agent_reports` 해소).
- **유지(경로만 정리)**: 핵심 루프 `orchestrator.py` `session.py` `executor.py` `journal.py`
  `prompts.py` 는 최상위 유지(hot — 불필요한 이동 금지).

**함수/심볼 네이밍 전수검사 (요구사항)**: 이동·개명 대상 모듈의 **모든** 정의·import·
호출·`monkeypatch` 타깃·문자열 경로 참조(`rg`로 전수)를 조사해 모듈 경로 + 모듈명에 묶인
함수/클래스명(예: `agent_reports.build_*`)을 정합되게 일괄 변경. 테스트는 내용 불변·green 유지.
재export shim은 두지 않고 호출부를 직접 갱신(monorepo-native, [[feedback-monorepo-refactor-as-native]]).

**외부 표면 점검(critic, 2026-06-08)**: in-repo만 영향(cron/runbook 참조 없음) — ① `equity_log.py:113`에
`__main__` 진입점 존재 → `python -m src.agent.equity_log`가 `…agent.logs.equity`로 바뀜(미문서화·저위험,
클린 브레이크로 새 경로 채택), ② `test_agent_reports.py:199`가 `"src.agent.agent_reports.os.replace"`를
**문자열 경로**로 monkeypatch(import 아님 — 문자열 전수검사로 포착), ③ `docs/DESIGN.md:310`이
`turn_log`/`equity_log`/`trades_log`를 이름으로 언급 → 동일 PR에서 갱신.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/agent/**` 광범위 + 호출부(`src/trading/modes/agent.py`,
  `src/agent/steering/runtime.py` 등) + `tests/` 광범위(import 경로).
- **API/시그니처 변경**: 모듈 경로/모듈명 다수 이동·개명(공개 함수 시그니처는 불변).
- **알려진 동시 변경 / 권장 순서**: 가장 넓은 구조 변경 → **다른 agent-touching 트랙이 없을 때
  단독 실행**. R10(intraday)·R13(tests)와 import/테스트가 겹침. 권장 순서: R9→R11→R12→R10→
  **R8**→R13 (R8은 큰 구조 변경이라 뒤쪽, R13은 최후).

## Stage Progress (skill: ai-dlc-refactor)
- [x] Stage 1 — Baseline (`1-baseline.md`; 9모듈 ~50참조 전수(문자열 7·모듈객체 import 2 포함); agent 테스트 158 green)
- [x] Stage 2 — Tier ledger (`2-tier-ledger.md`) — T1 7항목 + T3 1(기승인 -m 클린브레이크)
- [x] Stage 3 — Redesign (`3-redesign.md`) — logs/·learning/ 구조 + _log 접미사 제거 + 마이그레이션 순서
- [x] Stage 4 — Implementation — git mv 9 + import ~50(문자열 7·모듈객체 3) + gitignore negation + 이름충돌(orchestrator 로컬 reports) 함수직접import로 해소
- [x] post-merge-guide — -m 클린브레이크 + gitignore negation 노트
- [x] Build & Test — 전체 **1073 passed**; py_compile + 신규 9경로 import smoke OK
