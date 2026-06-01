# Multi-Agent Research 교차검증 + 시그널 확장 — Requirements

## 1. 의도 분석 (Intent Analysis)

- **요청**: 현재 단일 AI 세션이 수행하는 research turn을 N개 agent 교차검증 방식으로 개선 + 시그널 확장 + 모두 configurable
- **요청 유형**: Enhancement (기존 기능 확장)
- **범위**: Multiple Components (orchestrator, session, prompts, tools/market, settings, journal)
- **복잡도**: Complex (멀티세션 아키텍처 + 새 도구 + 설정 체계)

## 2. 기능 요건 (Functional Requirements)

### FR-1: 듀얼 모드 멀티에이전트 Research Turn

두 가지 실행 모드를 모두 구현하고, `settings.yaml`에서 선택 가능하게 한다.

**Mode B — Sequential Debate (단일 세션):**
- 하나의 `claude -p` 세션에서 N-1번의 시퀀셜 토론 후 Manager가 최종 판정
- 각 토론 라운드는 서로 다른 관점(분석 방향)에서 기존 분석을 평가·보완·반박
- 모든 도구(Q2의 A~D 시그널) 열람 가능
- N=1이면 현재 단일 세션과 동일하게 동작 (하위 호환)

**Mode C — Parallel Sub-agents (멀티 세션):**
- Manager 세션이 N-1개의 sub-agent를 launch
- 각 sub-agent는 별도 `claude -p` 세션으로 병렬 실행, **격리된 임시 workspace**에서 동작 (§NFR-4 참조)
- Manager가 sub-agent에게 서로 다른 업무를 분배 (분업), 모든 도구 열람 가능하되 prompt로 역할 구분
- sub-agent 완료 후 Manager가 모든 보고서(stdout `result` 반환)를 종합하여 최종 판정
- sub-agent의 `allowed_tools`는 **읽기 전용 + Bash(tools)만** 허용 (`Read`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, `Bash(python -m src.agent.tools:*)`). `Write`/`Edit` 미포함 — decisions.jsonl 기록은 구조적으로 불가능 (§NFR-4)
- sub-agent 세션은 **항상 fresh session ID** 생성 (`.sessions/<date>.json` 상태 파일을 사용하지 않음, one-shot 모드)

**공통:**
- `multi_agent.enabled=true`이면 N ≥ 2 강제 (N=1은 enabled=false와 동일)
- `multi_agent.enabled=false`이면 기존 단일 세션 방식 (현재 코드 그대로)
- 최종 결정은 항상 `decisions.jsonl`에 기록 (기존 Decision 스키마 유지)

### FR-2: General Agent 역할 (고정 역할 없음)

- 전문 역할(Technical/Fundamental/News/Macro)을 미리 고정하지 않음
- 대신 모든 agent에게 전체 시그널 도구(indicators, fundamentals, news, earnings, insider, macro 등)를 열람 가능하게 제공
- 프롬프트에 "필요한 지표를 확인할 수 있는 가이드"를 주어 agent가 자율적으로 분석 방향을 결정
- Mode C에서 Manager가 업무 분배 시 자연어로 역할을 지정 (구조적 역할 강제 아님)

### FR-3: 구조화된 결론 + 자유 텍스트 본문

- 각 agent의 분석 결과: 본문은 자유 텍스트(심층 분석), 마지막에 구조화된 결론 섹션 강제
- 구조화된 결론 형식 (각 종목별):
  ```
  ## Verdict
  - symbol: <TICKER>
  - action: BUY | SELL | HOLD | ADJUST_STOP
  - confidence: 0.0-1.0
  - stop: <price>
  - target: <price>
  - reason: <one-line>
  ```
- 이 구조화된 결론은 F22의 AI 탑바에서 research turn 정보로 활용 가능하도록 설계
- Manager(최종 판정자)가 `decisions.jsonl`에 기록하는 것은 기존 Decision 스키마 유지

### FR-4: 시그널 확장 — 새 도구 추가

모든 시그널은 `settings.yaml`의 `research.signals` 목록으로 on/off 가능 (FR-7 참조).

**1순위 (F23 트랙에 포함):**

| 시그널 | 도구 | 소스 | 출력 형태 |
|--------|------|------|----------|
| 어닝스 캘린더 | `earnings <SYM>` | yfinance `calendar` (+ `earnings_dates` if `lxml` available) | "earnings in N days, consensus EPS $X, last 4Q surprise history (lxml 필요, 없으면 calendar만)" |
| 내부자 거래 | `insider <SYM>` | yfinance `insider_transactions` | "최근 6개월 insider buy/sell 요약, 대규모 거래 하이라이트" |
| Short Interest | `fundamentals <SYM>` 확장 | yfinance `info` | shortRatio, shortPercentOfFloat — `_FUNDAMENTAL_KEYS`에 추가 (trivial) |
| Analyst Upgrades | `analyst_upgrades <SYM>` (독립 도구) | yfinance `upgrades_downgrades` (DataFrame) | 최근 5건 upgrade/downgrade 이력. dict 패턴과 다르므로 별도 도구 (critic #2) |
| 매크로 지표 | `macro` (새 도구) | yfinance `^TNX`, `DX-Y.NYB`, `GC=F`, `CL=F` 등 | compact 매크로 대시보드 |
| 기관 보유 | `institutional <SYM>` (독립 도구) | yfinance `institutional_holders` (DataFrame) | 기관 보유 비율, top 5 기관. DataFrame이므로 별도 도구 (critic #2) |

> **소셜 감성 제외 (critic #1)**: StockTwits API가 403 반환 (차단/폐쇄 확인됨). 무료 대안 부재로
> `sentiment` 도구는 F23 범위에서 제외. 향후 Reddit PRAW 등 대안 확보 시 별도 트랙으로 추가.

**미포함 (명시적 제외):**
- 10-K/10-Q 섹션 추출 (EdgarTools 의존성 추가 회피)
- Options Flow (자체 감지)

### FR-5: Retrospect/학습 메커니즘 개선

**귀속**: Manager 세션만 EOD에서 반성 수행.

**구조화된 레코드**: 현재 자유 텍스트 `lessons.md`를 구조화된 레코드로 전환.

```json
{
  "lesson_id": "L001",
  "date": "2026-05-27",
  "category": "entry_timing | exit_timing | risk_mgmt | regime | thesis | sizing | other",
  "signal_used": "RSI > 75 + SMA20 distance",
  "outcome": "chased overbought, reversed -3.2%",
  "takeaway": "Don't chase RSI>75 names after parabolic moves",
  "times_applied": 3
}
```

- 저장 형식: `workspace/lessons.jsonl` (구조화 레코드, 1행 1교훈)
- **쓰기 메커니즘**: 새 CLI 서브커맨드 `python -m src.agent.tools lesson add --category <cat> --signal "<sig>" --outcome "<out>" --takeaway "<take>"` — Python 코드가 구조화된 JSON 직렬화를 처리 (LLM이 Write 도구로 직접 JSON을 쓰면 형식 불안정 → critic #6). Agent는 이 Bash 도구를 호출.
- 기존 `lessons.md`는 **LLM이 읽는 human-readable 뷰**로 유지. `lesson add` 커맨드가 lessons.jsonl 기록과 동시에 lessons.md에도 bullet point를 append.
- `times_applied` 카운트는 초기에는 수동 (agent가 lesson을 인용할 때). 자동 카운팅은 향후 개선.
- 다음 날 research turn에서 Manager 세션에 최근 N개 lesson 주입 (N은 configurable)
- EOD 매일 수행 (현재 주기 유지)

### FR-6: 기존 Research Turn 완전 대체 (토글 가능)

- `multi_agent.enabled: true`이면 멀티에이전트 파이프라인 실행
- `multi_agent.enabled: false`이면 기존 단일 세션 방식 (`run_morning_research()` 현재 코드 그대로)
- 전환은 `settings.yaml` 변경 + 데몬 재시작으로 즉시 적용
- 기존 코드는 삭제하지 않음 (폴백)

### FR-7: Configurable 설정 체계

`config/settings.yaml`에 추가되는 설정 블록:

```yaml
multi_agent:
  enabled: true              # false → 기존 단일 세션
  mode: sequential           # sequential (Mode B) | parallel (Mode C)
  n_agents: 3                # [1, 5] 범위. enabled=true이면 2 이상 강제

research:
  signals:                   # 활성화할 시그널 목록 (여기 없으면 비활성)
    - quote
    - indicators
    - fundamentals           # short interest + analyst upgrades + 기관보유 포함
    - news
    - scoreboard
    - earnings               # 어닝스 캘린더
    - insider                # 내부자 거래
    - macro                  # 매크로 지표
  reflection:
    enabled: true
    max_lessons_injected: 10 # research turn에 주입할 최근 lesson 수

agent:
  research_start_before_open: 60  # 개장 N분 전에 research 시작 (기본 60 → 08:30 ET)
  research_end_before_open: 5     # 개장 N분 전까지 research 완료 (기본 5 → 09:25 ET)
  # → timeout = start_before_open - end_before_open = 55분 = 3300s (자동)
  # → 09:30 개장 기준: 08:30 시작, 09:25 마감
```

## 3. 비기능 요건 (Non-Functional Requirements)

### NFR-1: 비용/지연 제한
- 멀티에이전트 전체 비용 = 현재 research turn 대비 2~3× 이내
- Mode B: 단일 세션이므로 비용 ≈ 1.5~2× (더 긴 세션)
- Mode C: N 세션이므로 비용 ≈ N× (병렬이라 wall-clock은 비슷)
- **research_timeout 자동 계산**: `research_start_before_open - research_end_before_open`. 기본값: 60 - 5 = 55분 = 3300s. 시작을 더 앞당기면(예: 90) 자동으로 더 긴 timeout 확보 (85분).
- **hard deadline**: research turn이 개장 `research_end_before_open`분 전(기본 09:25 ET)까지 완료되지 않으면 진행 중인 sub-agent/세션을 강제 종료하고, 그때까지의 결과만으로 Manager가 판정 (fail-graceful, SECURITY-15)

### NFR-2: Advisor-Only 원칙 유지
- 멀티에이전트 구조에서도 **어떤 agent도 직접 주문을 넣지 않음**
- 최종 결정은 `decisions.jsonl`에 기록 → 기존 `DecisionExecutor` → `RiskManager` → `Broker` 경로 유지
- sub-agent는 분석만 수행, `decisions.jsonl` 기록은 Manager만 수행

### NFR-3: 기존 파이프라인 무중단
- `multi_agent.enabled=false`이면 현재 코드와 100% 동일하게 동작
- 멀티에이전트 코드가 기존 경로에 side-effect를 주지 않음
- 기존 테스트 전부 통과

### NFR-4: 세션 격리 (critic #3, #4, #8 반영)
- Mode C의 sub-agent 세션은 서로 독립 (각각 별도 `claude -p` 프로세스)
- **구조적 격리**: sub-agent는 **격리된 임시 workspace** (temp dir)에서 실행. 원본 workspace의 읽기 전용 참조 파일(theses, regime.md, watchlist.md, lessons.md)을 복사/심링크하되, `decisions.jsonl`은 포함하지 않음. 분석 결과는 stdout(JSON `result` 필드)로 반환, Manager가 수집.
- **allowed_tools 제한**: sub-agent의 `claude -p` 세션은 Write/Edit 미포함 (`Read`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, `Bash(python -m src.agent.tools:*)` 만). decisions.jsonl 기록은 구조적으로 불가능.
- **session ID 격리**: sub-agent는 `.sessions/<date>.json` 상태 파일을 사용하지 않음 (`one_shot=True` 모드로 항상 fresh session ID 생성). Manager 세션의 상태 파일과 충돌 없음.
- **decision counting 보호**: sub-agent는 별도 workspace이므로 `orchestrator._run()`의 before/after 카운트에 영향을 주지 않음. Manager만 원본 workspace에서 decisions.jsonl에 기록.

### NFR-5: F22 AI 탑바 호환
- FR-3의 구조화된 결론(Verdict 섹션)을 F22의 AI 탑바가 읽을 수 있는 형식으로 출력
- 구체적 형식은 F22 트랙과 조율 필요 (F22 의존)

## 4. 아키텍처 통합 포인트

### 변경 대상 모듈
| 모듈 | 변경 내용 |
|------|----------|
| `src/agent/orchestrator.py` | `run_morning_research()` → 멀티에이전트 분기 (enabled 여부) |
| `src/agent/session.py` | sub-agent 세션 launch 지원 (Mode C) |
| `src/agent/prompts.py` | 멀티에이전트 프롬프트 (역할 가이드, debate 구조, verdict 스키마) |
| `src/agent/tools/market.py` | `earnings()`, `insider()`, `macro()` 추가 + fundamentals 확장 |
| `src/agent/tools/__main__.py` | 새 서브커맨드 등록 |
| `src/agent/review.py` | 구조화된 retrospect 레코드 생성 |
| `src/agent/journal.py` | `lessons.jsonl` 읽기/쓰기 |
| `config/settings.yaml` | `multi_agent` + `research.signals` + `research.reflection` 블록 |
| `src/trading/modes/agent.py` | research turn에서 멀티에이전트 오케스트레이션 호출 |

### 변경하지 않는 것
- `DecisionExecutor` (decisions.jsonl → RiskManager → Broker 경로 불변)
- `RiskManager` / `BaseBroker` (하류 불변)
- 기존 intraday/EOD turn 흐름 (research turn만 영향)

### NFR-6: TurnCoordinator 상호작용 + 시간 제한 (critic #7 + 사용자 요청 반영)
- **research turn은 항상 개장 `end_before_open`분 전까지 완료된다** — timeout이 이를 보장.
  - `research_timeout = research_start_before_open - research_end_before_open` (자동 계산)
  - 기본: 60 - 5 = 55분 (08:30 시작, 09:25 마감).
  - `end_before_open ≥ start_before_open`이면 설정 오류 → fail-fast 에러.
- 이 보장 덕분에 **turn_lock 경합은 발생하지 않음** (research는 09:25 이전 종료, intraday는 09:30 이후 시작). 별도 lock 전략 불필요 — 기존 `try_scheduled_turn` 경로 유지 가능.
- **hard deadline 초과 시**: 진행 중인 sub-agent/세션을 강제 종료, 그때까지의 결과로 Manager 판정 (partial result, fail-graceful).
- `_premarket_research()` 호출부를 수정하여 멀티에이전트 분기 추가 (FR-6의 "기존 코드 그대로"는 `run_morning_research()` 함수 자체를 의미, 호출부 `_premarket_research`는 분기 필요).

## 5. Extension Configuration (F23)
- **Security Baseline**: Enabled. 적용 규칙: SECURITY-03 (no secrets in logs — API 키, broker 자격증명 로그 금지), SECURITY-11 (risk/auth logic isolated — 기존 RiskManager→Broker 게이트 불변), SECURITY-15 (explicit error handling, fail-closed — sub-agent 실패 시 Manager fallback). 대부분 N/A (no web app, DB, IaC).
- **Property-Based Testing**: Enabled — Partial mode. Pure function에만 PBT 적용 (verdict 파싱, lesson record round-trip, signal config validation). Framework: Hypothesis.

## 6. 제약 사항 및 가정
- sub-agent는 별도 `claude -p` 프로세스로 실행 (Mode C). `claude` CLI가 동시 다중 세션을 지원하는 것으로 가정 (각각 독립 workspace + fresh session ID로 충돌 회피).
- ~~StockTwits API~~ → **제외** (403 차단 확인됨, critic #1). 소셜 감성 도구는 F23 범위 밖.
- `lessons.jsonl` 구조화와 기존 `lessons.md` 자유 텍스트 양립 — `lesson add` CLI 커맨드가 양쪽에 동시 기록하여 이중 관리 오버헤드 완화.
- F22(AI 탑바)와의 verdict 형식 조율은 F22 진행 상태에 의존.
- `yfinance.earnings_dates`는 `lxml` 의존성 필요 — `lxml`을 dev/optional dep으로 추가하거나, `calendar`만으로 폴백.
- Mode C sub-agent의 workspace 격리를 위해 `AgentSession`에 `one_shot` 모드 + custom `allowed_tools` + custom workspace path 파라미터 추가 필요.

## 7. Worktree 전략
- 새 worktree + `feat/F23` 브랜치에서 작업
- main에 머지
- submodule 변경 없음 (Python-only)
