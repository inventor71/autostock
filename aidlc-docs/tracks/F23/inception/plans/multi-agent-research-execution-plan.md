# F23 Multi-Agent Research 교차검증 + 시그널 확장 — 실행 계획

## 상세 분석 요약

### 변환 범위 (Brownfield)
- **변환 유형**: Agent path 아키텍처 확장 (단일 세션 → 멀티에이전트)
- **주요 변경**: research turn 오케스트레이션 + 시그널 도구 확장 + retrospect 구조화
- **관련 컴포넌트**: orchestrator, session, prompts, tools/market, journal, modes/agent, settings

### 변경 영향 평가
- **사용자 대면 변경**: 없음 (내부 agent 의사결정 품질 개선)
- **구조적 변경**: 있음 (research turn 아키텍처: 단일→멀티 세션)
- **데이터 모델 변경**: 있음 (lessons.jsonl 구조화 레코드 추가)
- **API 변경**: 있음 (새 CLI 도구: earnings, insider, macro, lesson add)
- **NFR 영향**: 있음 (세션 격리, timeout/deadline, 비용 제어)

### 리스크 평가
- **리스크 수준**: Medium-High
  - research turn은 실시간 의사결정 경로 (advisor-only지만 decisions.jsonl에 직접 영향)
  - 멀티세션 병렬 실행 (Mode C)은 workspace 격리 필수
  - pre-market timing constraint (개장 전 완료 hard deadline)
- **롤백 복잡도**: 쉬움 (worktree 격리, `multi_agent.enabled=false` 즉시 폴백)
- **테스트 복잡도**: 중간 (세션 mock + timing + 격리 검증)

## 단위 분해 (Units)

2개 단위로 분해. Unit 1 먼저 (독립적), Unit 2가 위에 구축.

### Unit 1: `signal-tools` — 시그널 도구 확장 + retrospect 도구
도구 레이어 추가. Unit 2와 `journal.py` 의존성 존재 (아래 참조).

| 항목 | 내용 |
|------|------|
| 범위 | 새 독립 도구 (earnings, insider, macro, analyst_upgrades, institutional, lesson add) + fundamentals 확장 (short interest = `_FUNDAMENTAL_KEYS` 추가만) + settings `research.signals` + config 모델 |
| 의존성 | Unit 2와 `journal.py` 공유 — Unit 1에서 `LessonRecord` 스키마 + `Journal` lesson 메서드를 확정하고, Unit 2의 FD가 이를 참조 |
| 변경 파일 | `src/agent/tools/market.py`, `src/agent/tools/__main__.py`, `src/agent/journal.py` (lessons.jsonl + LessonRecord), `config/config.py` (MultiAgentConfig, ResearchConfig, AgentConfig 확장), `config/settings.yaml` |
| 리스크 | Low (순수 추가, 기존 경로 불변) |

> **Critic #2 반영**: analyst upgrades (`ticker.upgrades_downgrades` → DataFrame)와 institutional holders
> (`ticker.institutional_holders` → DataFrame)는 기존 `_FUNDAMENTAL_KEYS` dict 패턴과 다르므로, `fundamentals()`
> 에 섞지 않고 **별도 독립 도구**로 분리. Short interest만 `_FUNDAMENTAL_KEYS`에 추가 (trivial).
>
> **Critic #1 반영**: `config/config.py`에 `MultiAgentConfig`, `ResearchConfig` Pydantic 모델 추가 +
> `AgentConfig`에 `research_start_before_open`/`research_end_before_open` 필드 추가. `Settings`의
> `extra: "ignore"` 때문에 모델에 선언하지 않으면 조용히 무시됨.
>
> **Critic #4 반영**: `journal.py` 변경이 Unit 1/2 공유. Unit 1에서 `LessonRecord` + lesson 메서드 시그니처를
> 확정하고 문서화하여, Unit 2 FD가 참조할 수 있게 함.

### Unit 2: `multi-agent-orchestration` — 멀티에이전트 research turn
핵심 아키텍처 변경. Unit 1의 도구를 활용.

| 항목 | 내용 |
|------|------|
| 범위 | Mode B(sequential debate) + Mode C(parallel sub-agents) 구현, AgentSession 확장(one_shot, restricted tools, isolated workspace), 멀티에이전트 프롬프트, research timing(start/end_before_open), orchestrator 분기 |
| 의존성 | Unit 1 (새 도구 + lesson CLI) |
| 변경 파일 | `src/agent/orchestrator.py`, `src/agent/session.py`, `src/agent/prompts.py`, `src/trading/modes/agent.py`, `config/settings.yaml`, `config/config.py` (AgentConfig timing fields) |
| 리스크 | Medium-High (live research path, 멀티세션 격리, timing) |

> **Critic #3 반영**: 기존 `agent.research_timeout: 1800` 키와의 하위 호환. 우선순위:
> `research_timeout`(명시) > 자동 계산(`start_before_open - end_before_open`). 양쪽 모두 있으면
> 명시값 사용 + deprecation 경고 로그. Unit 2 FD에서 마이그레이션 경로 정의.
>
> **Critic #5 반영**: Mode C sub-agent 스폰 시 `AGENT_JOURNAL_ROOT` 환경변수를 **격리 temp workspace로
> override** (또는 unset). 현재 daemon이 `agent.py:58`에서 설정하고 sub-agent가 상속하면 격리 깨짐.
> Unit 2 NFR Design에서 env 스크러빙 명시.
>
> **Critic #6 반영**: Mode B `_run()` wrapping — 멀티라운드 debate 전체를 하나의 `_run()` 호출로 감싸서
> decision counting이 최종 Manager verdict만 캡처. Unit 2 FD에서 명시.

## 단계 판정

### INCEPTION PHASE
- [x] Workspace Detection — COMPLETED (brownfield, 기존 프로젝트)
- [x] Reverse Engineering — reused (아티팩트 존재)
- [x] Requirements Analysis — COMPLETED & APPROVED
- [x] User Stories — **SKIP** (내부 agent 아키텍처 변경, 사용자 대면 없음)
- [x] Workflow Planning — IN PROGRESS (본 문서)
- [ ] Application Design — **SKIP** (컴포넌트 경계 명확, Functional Design에 흡수)
- [ ] Units Generation — **SKIP** (본 실행 계획에서 2개 unit 정의 완료)

### CONSTRUCTION PHASE — Unit 1 (`signal-tools`)
- [ ] Functional Design — **SKIP** (short interest = `_FUNDAMENTAL_KEYS` 추가, 나머지는 독립 도구로 분리하여 기존 패턴 반복. DataFrame 도구의 출력 형식은 Code Gen plan에서 정의)
- [ ] NFR Requirements — **SKIP** (추가 의존성 없음, optional lxml만)
- [ ] NFR Design — **SKIP** (순수 추가, 기존 패턴)
- [ ] Infrastructure Design — **SKIP** (로컬 CLI)
- [ ] Code Generation — **EXECUTE**

### CONSTRUCTION PHASE — Unit 2 (`multi-agent-orchestration`)
- [ ] Functional Design — **EXECUTE** (Mode B/C 상세 흐름, 프롬프트 설계, sub-agent lifecycle, verdict 합산 로직, `_run()` wrapping 전략, `research_timeout` 마이그레이션)
- [ ] NFR Requirements — **EXECUTE (minimal)** (세션 격리, timeout/deadline, 0 new runtime deps)
- [ ] NFR Design — **EXECUTE** (workspace 격리 구현 + AGENT_JOURNAL_ROOT env 스크러빙, one_shot 세션, allowed_tools 제한, fail-graceful deadline, research timing 계산)
- [ ] Infrastructure Design — **SKIP** (로컬 CLI/daemon)
- [ ] Code Generation — **EXECUTE**

### BUILD & TEST (전체)
- [ ] Build and Test — **EXECUTE** (두 unit 합산: regression + 새 도구 테스트 + 멀티에이전트 integration + PBT)

### OPERATIONS PHASE
- [ ] Operations — PLACEHOLDER

## 실행 순서

```
Unit 1: signal-tools
  └─ Code Generation (Part 1: plan → Part 2: build)
       ↓
Unit 2: multi-agent-orchestration
  ├─ Functional Design
  ├─ NFR Requirements (minimal)
  ├─ NFR Design
  └─ Code Generation (Part 1: plan → Part 2: build)
       ↓
Build & Test (전체 통합)
```

## 텍스트 워크플로 시각화

```
Phase 1: INCEPTION
  - Workspace Detection .............. COMPLETED
  - Reverse Engineering .............. REUSED
  - Requirements Analysis ............ COMPLETED
  - User Stories ..................... SKIP
  - Workflow Planning ................ COMPLETED
  - Application Design .............. SKIP (→ Functional Design)
  - Units Generation ................. SKIP (본 계획에 정의)

Phase 2: CONSTRUCTION — Unit 1 (signal-tools)
  - Functional Design ................ SKIP
  - NFR Requirements ................. SKIP
  - NFR Design ....................... SKIP
  - Infrastructure Design ........... SKIP
  - Code Generation .................. EXECUTE

Phase 3: CONSTRUCTION — Unit 2 (multi-agent-orchestration)
  - Functional Design ................ EXECUTE
  - NFR Requirements ................. EXECUTE (minimal)
  - NFR Design ....................... EXECUTE
  - Infrastructure Design ........... SKIP
  - Code Generation .................. EXECUTE

Phase 4: BUILD & TEST
  - Build and Test ................... EXECUTE
```

## 성공 기준
- **1차 목표**: `multi_agent.enabled=true`로 research turn이 N=3 agent 교차검증으로 실행되고, `enabled=false`면 기존과 동일
- **주요 산출물**:
  - 7개 시그널 변경: 새 독립 도구 5개 (earnings, insider, macro, analyst_upgrades, institutional) + `_FUNDAMENTAL_KEYS` short interest 확장 + `lesson add` CLI
  - `lesson add` CLI 도구 + lessons.jsonl 구조화
  - Mode B (sequential debate) + Mode C (parallel sub-agents) 구현
  - `research_start_before_open` / `research_end_before_open` timing 제어
  - settings.yaml 설정 체계
- **품질 게이트**: 기존 테스트 전부 통과 + 새 도구 단위 테스트 + 멀티에이전트 통합 테스트 + PBT (verdict 파싱, lesson round-trip)
