# F29 — Supervisor 모드 코드베이스 오리엔테이션 요구사항

> **Track**: F29 · **Type**: Feature (Enhancement) · **Brownfield** · **Depth**: Minimal
> **Source**: `F29-requirement-verification-questions.md` (Q1–Q8, 2026-06-01)
> **Base commit**: bb2da2d

## 1. 의도 분석 (Intent Analysis)

- **User Request**: Supervisor 모드에서 에이전트가 코드베이스 구조를 몰라 경로 시행착오를 함 (`/app/src/main.py` → File not found). 프로젝트 구조 맵을 제공해 첫 턴부터 정확한 파일을 읽을 수 있게 개선.
- **Request Type**: Enhancement — 기존 F26 supervisor 권한 프로파일 위에 지식 레이어 추가
- **Scope**: Multiple Components — 데몬(Python): 코드베이스 트리 생성 · MCP 서버(TS): `steer_read` 뷰 확장 · 런처(TS): supervisor system prompt 지침 추가
- **Complexity**: Simple — 변경량 적고, F26 권한 변경 없음, 기존 publish/snapshot 패턴 재사용

## 2. 기능 요구사항 (Functional Requirements)

### FR-1 — `steer_read` MCP에 `/codebase` 뷰 추가 (Q1=C)

`steer_read{command:/codebase}` 호출 시 프로젝트 디렉터리 트리를 반환한다.

- **메커니즘**: 데몬이 시작 시 `$AUTOSTOCK_ROOT` 기준 디렉터리 트리를 스캔해 `steering/codebase.json`에 기록하고, MCP `steer_read`의 `/codebase` verb가 이 파일을 읽어 반환.
- **기존 패턴 재사용**: `monitor.json`을 `/turns`, `/decisions`, `/log` verb로 조회하는 것과 동일한 패턴 (`MONITOR_VERBS` 확장 또는 별도 파일).

### FR-2 — 디렉터리 트리 내용 (Q2=A)

탑레벨 디렉터리 + `src/` 하위 패키지의 2레벨 트리, 각각 한 줄 설명 포함:

```
autostock/                         # AUTOSTOCK_ROOT
├── main.py                        # CLI 진입점 (모드 디스패치)
├── src/                           # Python 애플리케이션 코드
│   ├── agent/                     # 에이전트 모드 — LLM PM + 저널 + 결정 실행 + steering
│   │   ├── orchestrator.py        # 에이전트 턴 시퀀싱 (research/intraday/EOD)
│   │   ├── session.py             # claude CLI 서브프로세스 래퍼
│   │   ├── executor.py            # DecisionExecutor — 결정→주문 실행 (유일한 주문 경로)
│   │   ├── journal.py             # 파일 기반 저널 (workspace/decisions.jsonl)
│   │   ├── prompts.py             # LLM 프롬프트 템플릿
│   │   ├── review.py              # EOD 자체 평가
│   │   ├── tools/                 # 에이전트 MCP 도구 (market/account/news/watch)
│   │   ├── intraday/              # F3 — 실시간 wake/브리프/이상감지
│   │   └── steering/              # F4 — 운영자 steering 엔진 (bus/turns/state/channel/commands)
│   ├── trading/                   # 트레이딩 엔진 + 모드
│   │   ├── engine.py              # TradingEngine — 전략 경로 per-symbol 사이클
│   │   └── modes/                 # agent / paper / live / backtest 모드
│   ├── strategy/                  # 전략 구현체
│   │   ├── technical/             # MA Crossover, RSI, MACD, Bollinger
│   │   ├── ml/                    # Random Forest, LSTM
│   │   └── llm/                   # LLM 전략 (Claude/OpenAI)
│   ├── risk/                      # 리스크 관리
│   │   └── manager.py             # RiskManager — 모든 주문의 단일 게이트 (신호→Order)
│   ├── execution/                 # 브로커 추상화
│   │   ├── base.py                # BaseBroker (SimulatedBroker, AlpacaBroker)
│   │   └── alpaca_broker.py       # Alpaca API 구현체
│   ├── data/                      # 데이터 수집/변환 (yfinance, Alpaca, intraday features)
│   ├── core/                      # 공통 Pydantic 모델/타입 (다른 패키지가 의존, core는 독립)
│   └── config/                    # 설정 (pydantic-settings, settings.yaml 로드)
├── operator-console/              # 오퍼레이터 콘솔 (opencode 하드포크, TypeScript)
│   ├── cli/                       # opencode fork — TUI + permission engine
│   ├── launcher/                  # autostock 런처 (config.ts, cli.ts)
│   └── src/                       # MCP 서버 (mcp-server.ts, steer-handler.ts)
├── config/                        # YAML 설정 파일 (settings.yaml, strategies.yaml)
├── tests/                         # Python 테스트
├── docs/                          # 설계 문서 (DESIGN.md)
├── scripts/                       # 유틸리티 스크립트 (agent_trace.py 등)
├── workspace/                     # 에이전트 런타임 데이터 (저널, turns, decisions)
├── steering/                      # 운영자 steering 채널 (snapshot.json, monitor.json, commands)
└── aidlc-docs/                    # AI-DLC 설계 문서 (요구사항, 디자인, 트랙)
```

- **경로 표기**: `AUTOSTOCK_ROOT` 기준 상대경로 + 루트에는 `{AUTOSTOCK_ROOT}` 명시 (Q3=A). 에이전트는 `echo $AUTOSTOCK_ROOT`로 확인 후 상대경로와 조합.
- **주요 파일**: 각 패키지별 핵심 파일 1~2개와 그 역할을 한 줄로 표기.

### FR-3 — 데몬이 코드베이스 맵 생성 및 발행 (Q4=D)

- 데몬 시작 시 `$AUTOSTOCK_ROOT` 디렉터리 트리를 1회 스캔해 `steering/codebase.json`에 기록.
- 스캔 대상: `src/`, `operator-console/`, `config/`, `tests/`, `docs/`, `scripts/` (`__pycache__`, `.git`, `node_modules`, `.mypy_cache` 등 제외).
- 패키지 설명은 데몬 코드에 하드코딩된 사전(Map)에서 조회. (구조 변경은 드물고, 사람이 의도한 설명이 필요하므로 자동 추출보다 사전 방식.)
- `publish_monitor`와 동일한 주기로 갱신 가능하지만, 소스 구조는 런타임에 변하지 않으므로 시작 시 1회 생성으로 충분.

### FR-4 — MCP `steer_read` 확장

`operator-console/src/steer-handler.ts`의 `handleSteerRead`에 `/codebase` verb 추가:
- `steering/codebase.json`을 `FileDrop`으로 읽어 트리 텍스트를 반환.
- `/why`, `/turns` 등과 동일한 패턴으로 구현. `MONITOR_VERBS`에 추가하거나 codebase는 별도 파일(`codebase.json`)에서 읽도록 분기.

### FR-5 — Supervisor system prompt에 최소 지침 추가 (Q6=B)

런처가 supervisor 모드(`--supervisor`)로 콘솔을 기동할 때, opencode config `instructions`에 다음 1~2줄의 지침을 추가:

```
autostock 코드베이스에 대해 질문받으면, 먼저 steer_read{command:/codebase}로 프로젝트 구조를 확인하세요.
모든 소스 파일은 AUTOSTOCK_ROOT(echo $AUTOSTOCK_ROOT로 확인) 기준 상대경로로 접근합니다.
```

- `config.ts`의 `consoleEnv()`에서 supervisor일 때만 `instructions` 필드에 인라인 텍스트로 추가.
- 또는 opencode.json에 `instructions` 배열로 supervisor 전용 파일 경로 지정.
- 구현은 런처(TS) 변경 — 데몬(Python) 불변.

### FR-6 — Supervisor only, normal 제외 (Q7=B)

- `/codebase` 뷰는 `steer_read` MCP의 일부이므로, normal 모드에서도 도구 자체는 보임(MCP 도구 목록에 `steer_read`가 있으므로).
- 하지만 **system prompt 지침**(FR-5)은 supervisor에서만 주입되므로, normal 에이전트는 `/codebase`의 존재를 모르거나 사용을 권장받지 않음.
- 만약 normal 에이전트가 우연히 `/codebase`를 호출해도 문제 없음 — 코드 구조 정보를 아는 것 자체는 해가 되지 않으며, F26 권한 프로파일이 normal의 코드 읽기를 차단하므로 정보만으로는 접근 불가.

## 3. 비기능 요구사항 (NFR)

- **NFR-1 (F26 불변)**: F26 권한 프로파일 변경 없음 (Q5a=A). read/glob/grep/lsp 허용 범위 그대로.
- **NFR-2 (데몬 영향 최소)**: 코드베이스 트리 스캔은 시작 시 1회만 실행. 런타임 성능 영향 없음.
- **NFR-3 (Docker 호환)**: AUTOSTOCK_ROOT 기준 상대경로만 사용하므로 Docker(`/app`)·호스트 모두 추가 처리 없이 동작 (Q8=A).
- **NFR-4 (F28 독립)**: F28(normal UI 지식)과 메커니즘 공유 없음 — 별도 트랙, 별도 구현 (Q5b=A).

## 4. 변경 표면 (Surface Area)

| 컴포넌트 | 파일 | 변경 내용 |
|----------|------|----------|
| **데몬 (Python)** | `src/agent/steering/runtime.py` | 시작 시 코드베이스 트리 생성 → `steering/codebase.json` 발행 |
| **데몬 (Python)** | `src/agent/steering/channel.py` | `publish_codebase()` 또는 `publish_monitor` 확장 (codebase key 추가) |
| **MCP (TS)** | `operator-console/src/steer-handler.ts` | `MONITOR_VERBS`에 `/codebase` 추가 + `FileDrop` 읽기 |
| **MCP (TS)** | `operator-console/src/filedrop.ts` | `codebase.json` 읽기 헬퍼 추가 (선택적 — `readMonitor` 재사용 가능) |
| **런처 (TS)** | `operator-console/launcher/config.ts` | `consoleEnv()`에서 supervisor 시 system prompt 지침 추가 |

## 5. 확장 구성 (Extension Configuration)

F29는 기존 F26 권한 프로파일 위에서 동작하며, 새 보안 표면을 만들지 않음:
- **Security Baseline**: 프로젝트 기본값 유지 (Enabled). SECURITY-03(no secrets in codebase map) 적용 — 디렉터리 트리에 파일명만, 내용/경로에 비밀 없음.
- **Property-Based Testing**: Partial 유지. 순수 함수(트리 생성, 경로 필터링)에 Hypothesis 적용.

> **기본 구성**: 프로젝트 `aidlc-state.md` Extension Configuration을 그대로 사용.
