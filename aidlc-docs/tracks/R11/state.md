# Track R11 — `strategy/` 파일·클래스 네이밍 일관화

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R11
- **Title**: `strategy/` 파일 접미사 통일(`_strategy` 제거) + stutter 해소
- **Type**: refactor
- **Status**: backlog  <!-- not started; pick up via /ai-dlc-refactor R11 -->
- **Branch**: refactor/R11 (TBD)
- **Worktree**: .claude/worktrees/R11 (TBD)
- **Submodule branch**: — (Python only)
- **Base commit**: 2a4e02f (survey point; rebase when picked up)
- **Start Date**: TBD

## Extension Configuration
- **Security Baseline**: N/A.
- **Property-Based Testing**: N/A.

## Scope
strategy 파일 접미사가 뒤섞여 있다(점검 #5, MEDIUM):
- `technical/`: `bollinger.py` `ma_crossover.py`(접미사 X) vs `macd_strategy.py` `rsi_strategy.py`(`_strategy`)
- `ml/`: `lstm_strategy.py` `rf_strategy.py` vs `base_ml.py` `feature_eng.py`
- `llm/llm_strategy.py` → `llm.llm_strategy` **stutter**

**규칙: 디렉터리가 이미 분류하므로 모듈명에서 `_strategy` 접미사 제거** — 순수 T1:
- `technical/macd_strategy.py`→`technical/macd.py`, `rsi_strategy.py`→`technical/rsi.py`
  (bollinger/ma_crossover와 일관).
- `ml/lstm_strategy.py`→`ml/lstm.py`, `rf_strategy.py`→`ml/rf.py`.
- `llm/llm_strategy.py`→`llm/strategy.py` (stutter 해소).
- 클래스명(`MACDStrategy` 등)은 **유지**(모듈명만 정리) — Stage 3에서 최종 확정.

**함수/심볼 네이밍 전수검사 (요구사항)**: import·호출·`monkeypatch`를 `rg`로 전수 조사 후 일괄 변경.
**확인됨(critic, 2026-06-08)**: 전략 문자열 키는 `@register_strategy("macd")` **데코레이터 리터럴**
(`technical/macd_strategy.py:14` 등)이라 **파일명과 decoupled** — 모듈 파일 개명이 키를 건드리지 않는다.
`config/strategies.yaml`의 키(`macd`/`rsi`/`llm`…)·`class:` 값도 영향 없음. 클래스명도 유지(`R11:33`).
유일한 in-repo 결합은 `src/benchmark/runner.py:17-20`의 등록 import(전수검사로 포착). → **순수 T1**.
(전략 키 자체는 혼동 대상이 아니므로 **그대로 유지** — 클린 브레이크 불필요.)

## Merge Risk Notes
- **공유 파일 (주의)**: `src/strategy/**` + `src/strategy/registry.py` + `tests/` 전략 테스트.
- **API/시그니처 변경**: 모듈명 5건 개명(클래스명·전략 키 불변).
- **알려진 동시 변경 / 권장 순서**: strategy는 다른 R-트랙과 거의 안 겹침(`benchmark/runner.py` import만) → R9 다음(R11) 권장.

## Stage Progress (skill: ai-dlc-refactor)
- [ ] Stage 1 — Baseline (`benchmark/runner.py` 등록 import 등 모듈경로 사용처 인벤토리; 테스트 green)
- [ ] Stage 2 — Tier ledger (all-T1 — 모듈 파일 개명만; 키·클래스 불변)
- [ ] Stage 3 — Redesign (모듈명 매핑 + 클래스명 유지 여부 + registry 갱신)
- [ ] Stage 4 — Implementation (개명 + 전수 호출부/키 갱신)
- [ ] Build & Test
