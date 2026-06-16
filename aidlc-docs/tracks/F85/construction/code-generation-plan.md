# F85 — Code Generation Plan

> worktree feat/F85. 의존순서. 각 단계 완료 즉시 [x]. functional-design.md 기준.

## 1. 설정 계층
- [x] `config/config.py` — `AggressivenessLevel = Literal[...]`; `AgentConfig.aggressiveness="balanced"` + `field_validator(mode="before")` fail-safe(비멤버→balanced+warn)
- [x] `config/settings.yaml` — `agent.aggressiveness: balanced` 주석 포함

## 2. SSOT preset 모듈
- [x] `src/agent/aggressiveness.py` (NEW) — `AggressivenessProfile`(frozen), `ALLOWED_RISK_KEYS`, `PROFILES`(3레벨, balanced=현행), `resolve(level)` fail-safe, disposition/churn/short_tilt 문구, grading_horizon_days, recall_recency

## 3. Decision 스탬핑 (C1)
- [x] `src/agent/journal.py` — Decision에 `aggressiveness="balanced"`, `grading_horizon_days=20` (legacy default)
- [x] `src/agent/orchestrator.py` — `_stamp_new`에서 두 필드 세팅(prompt_version 자리)

## 4. 리스크 overlay (FR-3/FR-6, use_bracket_orders per-site)
- [x] `main.py` — `_build_risk_manager`에 profile overlay(named allowlist), 에이전트 경로 합류, `use_bracket_orders` per-site 유지; startup 로그(FR-5)

## 5. 프롬프트 팬아웃 (delta 주입; balanced=빈문자열)
- [x] `src/agent/prompts.py` — 7 빌더에 disposition/churn/short_tilt 인자
- [x] `src/agent/orchestrator.py` — 전 빌더 호출부 주입 + `main.py` aggressiveness 주입

## 6. 학습 — C3 maturity/grade/normalize, C4 recency
- [x] `src/agent/quality/collector.py` — maturity 게이트, OPEN slice `[ts,ts+horizon]`, fetch end(max horizon/closed_at/today), human 제외, `grade_matured`+`grades.jsonl`(decision_index+ts, EOD 전용)
- [x] `src/agent/quality/models.py` — DecisionOutcome에 mature/holding_days 필요시
- [x] `src/agent/learning/efficacy.py` — excess per-day 정규화(`/max(holding_days,1)`)
- [x] `src/agent/orchestrator.py` — `recall_lessons(..., weights=RecallWeights(recency=profile.recall_recency))`; EOD에서 `grade_matured` 호출

## 7. F74 검증 자산
- [x] `evals/tests.yaml` — `aggressive-momentum-daytrade`/`conservative-value-hold` 시나리오 + `guidance_label`

## 8. 테스트
- [x] `tests/` — unit(validator/resolve/overlay shorting_enabled 불변/use_bracket_orders True/Decision round-trip/빌더 전수/maturity 경계/grade 멱등/human 제외/per-day norm)
- [x] property(hypothesis) — resolve fail-safe, maturity 경계
- [x] 실행: `venv/bin/python -m pytest` 관련 + typecheck
