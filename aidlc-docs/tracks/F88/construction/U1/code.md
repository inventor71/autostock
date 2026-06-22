# F88 / U1 — TriggerStore & models & AstScreen (construction record)

> 단위별 Functional Design + Code Generation 압축 기록 (autonomy: 설계 승인 후 자율 진행).

## Functional Design 요지
- **모델**(`src/agent/triggers/models.py`): `SourceRef`(signal|webfetch; websearch 제외 — critic#2),
  `Verdict`(fire 엄격 bool 강제=fail-closed, why 500자 truncate), `TriggerSpec`(id slug 검증·thesis·
  cadence hourly|daily·expires tz-aware 정규화·is_expired·wake_symbol "MACRO" fallback),
  `TriggerState`(daemon 전용), `TriggerSummary`/`TriggerDetail`(list/inspect 뷰).
- **저장**(`store.py`): `workspace/triggers/<id>/{spec.json(canonical)·predicate.py·state.json·
  trigger.md(rendered view)}`. **trigger.md는 생성 뷰, 파싱 안 함** → round-trip은 spec.json 기준
  (설계 §2의 frontmatter 방식에서 엔지니어링 정제: canonical JSON이 round-trip 견고). atomic_write_text
  (torn-safe) 재사용. register=create-only(중복/만료/oversize/screen-fail/MAX 백스톱 거부),
  active_specs(만료·disabled 제외), update_state(daemon single writer), cancel.
- **AST 스크린**(`ast_screen.py`): import allowlist(math/json/re/datetime/… ) + banned builtins
  (eval/exec/open/compile/__import__/getattr…) + dunder 접근 차단 + should_fire 진입점 강제 +
  relative/async 거부. **경계 아님(컨테이너가 경계), defense-in-depth.**
- `records.py` `WakeKind` Literal에 `agent_trigger` 추가.

## PBT (Partial: 02/03/07/08)
- PBT-02: spec/Verdict JSON round-trip 동등(`test_models_pbt.py`).
- PBT-03: future spec 미만료 / 만료 후 항상 만료(TTL 단조) / wake_symbol 비어있지 않음.
- PBT-07: 도메인 생성기(id regex, 알려진 signal, 미래 expires). PBT-08: Hypothesis 기본 shrink/seed.

## 검증
- `pytest tests/triggers/` → **56 passed** (main venv python3.12).
- import 스모크 OK. ruff 미설치(스킵).

## Security 컴플라이언스 (U1 적용분)
- SECURITY-05(입력검증): id slug/thesis/predicate 크기 cap/AST 스크린 ✔
- SECURITY-13(안전 역직렬화): spec/state는 pydantic 스키마 검증 역직렬화만; Verdict fire 엄격 bool ✔
- SECURITY-15(fail-closed): Verdict 비-bool fire → ValidationError(truthy fire 방지) ✔
- 06/07/09/10/14는 U2/U5에서 (N/A for U1).

## 파일
- 신규: `src/agent/triggers/{__init__,models,store,ast_screen}.py`,
  `tests/triggers/{__init__,test_models,test_ast_screen,test_store,test_models_pbt,test_wake_kind}.py`
- 수정: `src/agent/intraday/records.py` (WakeKind +agent_trigger)
- 커밋: 보류 (사용자 요청 시 — "commit only when asked")
