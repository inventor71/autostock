# Track F61 — 리서치 턴 주식 시그널 강화 (시장 무버/뉴스 catalyst + 종목 간 read-through)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F61
- **Title**: 리서치 턴 주식 시그널 강화 — 시장 무버/뉴스 catalyst 포착 + 종목 간 read-through 전파
- **Type**: feature
- **Status**: merged → main 1437d44 (2026-06-05)
- **Branch**: feat/F61 (merged)
- **Worktree**: .claude/worktrees/F61
- **Submodule branch**: — (parent-repo Python 예상; operator-console 변경 없으면 N/A)
- **Base commit**: e8b112b
- **Start Date**: 2026-06-05

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | No | Requirements Analysis |
| Property-Based Testing | Partial (pure functions / serialization round-trips) | Requirements Analysis |

- **Security Baseline**: Disabled — 내부 데이터 수집 도구. 단, 신규 API 키(FINNHUB_API_KEY)는 env-only·fail-honest 원칙 준수(룰 강제 아님, 관행 유지).
- **Property-Based Testing**: Partial — 순수 함수(피어맵 해석, 변화율/무버 임계 판정, 레코드 직렬화 round-trip)에 PBT 강제.

## Scope
리서치 턴의 데이터 수집 공백을 메운다. 진단(직전 대화) 결과 확인된 구조적 빈틈:
1. 뉴스가 종목별 pull + 에이전트 직접 호출 구조 → 시장 전체 catalyst surfacing 부재
2. 뉴스 소스 단일(yfinance) + 제목 키워드 감성 휴리스틱
3. 전부 일봉 기반 → 애프터아워스/실적 갭 사각지대
4. surge 감지기는 EOD·유니버스 한정·일봉·사후 기록용 (선제 전파 없음)
5. **종목 간 전파(contagion/read-through) 모델링 부재** — 핵심 공백
   (AVGO 실적 폭락 → 반도체/AI-capex 피어 리스크를 자동 연결하는 데이터 없음)
6. 실적 캘린더 awareness 부재 (per-symbol pull만)

세부 범위는 Requirements Analysis에서 확정. 관련: [[llm-trader-redesign]], [[risk-execution-redesign]].
계기: 브로드컴(AVGO) 실적 폭락을 autostock이 캐치하지 못함.

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. 비워두면 `/ai-dlc-merge`가 `git diff --name-only`로 자동 추론.

- **변경 파일 (8 수정 + 13 신규)**: 수정 = `config/config.py`(signals/finnhub 필드), `config/settings.yaml`(signals 블록), `main.py`(_make_signal_brief_provider), `pyproject.toml`(addopts), `src/agent/orchestrator.py`(signal_brief_provider), `src/agent/prompts.py`(signal_brief 인자 + 툴가이드), `src/agent/tools/market.py`(movers/readthrough/earnings_calendar), `src/agent/tools/__main__.py`(서브커맨드). 신규 = `src/signals/**`, `tests/signals/**`.
- **API/시그니처 변경**: 전부 additive·하위호환 — `morning_research_prompt`/`multi_research_initial_prompt`에 optional `signal_brief=None` 추가, `AgentTradingLoop.__init__`에 optional `signal_brief_provider=None` 추가. 기존 호출부 무영향.
- **알려진 동시 변경**: F59/F60(숏)이 `prompts.py`의 `_SHORT_GUIDANCE`/`_SIGNAL_TOOL_GUIDE` 영역 접근 가능 — 본 트랙은 dict 끝에 3개 키 추가 + 함수 시그니처만 변경, 충돌 가능성 낮음. rebase 시 `_SIGNAL_TOOL_GUIDE` 병합 확인.

## Stage Progress
- [x] Workspace Detection — brownfield (기존 코드 60+ 트랙); 타깃 서브시스템(research/data-collection)은 직전 진단 턴에서 분석 완료 → 전체 reverse engineering 생략
- [x] Requirements Analysis — depth: standard. 결정: A+B+C 묶음 / Alpaca뉴스+Finnhub무료+yfinance / 정적맵+LLM / push+툴 / 유니버스+bellwether / 유닛+AVGO재현. requirements.md 작성 완료
- [x] User Stories — SKIP (단일 운영자·내부 에이전트 도구·요구사항 구체적)
- [x] Workflow Planning — execution-plan.md 작성. 실행: Functional Design → Code Gen → Build & Test. 생략: App Design / Units / NFR Req·Design / Infra Design
- [x] Application Design — SKIP (additive, 기존 구조 위; 경계는 Functional Design에 흡수)
- [x] Units Generation — SKIP (단일 응집 유닛 market-signals)
- [ ] Construction — 단일 유닛 `market-signals`
  - [x] Functional Design — 승인됨(domain-entities/business-logic-model/business-rules)
  - [ ] NFR Requirements — SKIP (requirements.md에 포착; PBT-09=Hypothesis는 Functional Design 노트)
  - [ ] NFR Design — SKIP (기존 primitive 재사용)
  - [ ] Infrastructure Design — SKIP (infra 변경 없음)
  - [x] Code Generation — EXECUTE (commit cf3bb44: src/signals/ + 배선; 51 signals tests)
- [x] Build & Test — 60 signals + 847 full passing, 회귀 없음. 라이브 스모크(readthrough AVGO/SMH/XLE, Finnhub) ✅. code-review 5건 수정(commit 0039f6a). Status→merge-awaiting
