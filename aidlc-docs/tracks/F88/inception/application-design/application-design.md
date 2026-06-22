# F88 Application Design (standard)

> 신규 컴포넌트 경계·책임·인터페이스·의존·통합 지점 정의. 코드 그라운딩: `wake.py`, `turns.py`,
> `records.py`, `session.py`, `signals/collector.py` 실제 시그니처 확인 후 작성.

## 1. 컴포넌트 맵 (제안 패키지: `src/agent/triggers/`)

| 컴포넌트 | 책임 | plane |
|----------|------|-------|
| `TriggerStore` | `workspace/triggers/<id>/` CRUD, spec 직렬화/검증, predicate.py 보관, state.json 관리 | control(신뢰) |
| `TriggerSpec` / `Verdict` (모델) | spec·verdict pydantic 모델 + 직렬화 round-trip | control |
| `AstScreen` | predicate.py 정적 검사(차단 import/호출 거부) | control |
| `SandboxRunner` | predicate를 일회용 Docker로 실행, ctx 주입, verdict 파싱, fail-closed | execution 호출자(control)/실행(불신) |
| `BrokeredFetcher` | 선언 소스(signals collector + httpx-webfetch allowlist; websearch 후속) → `ctx.json`, TTL 캐시 | control |
| `TriggerEvaluator` | cadence 루프, rate-limit, TTL/만료, 연속에러 비활성화, fire→WakeEvent | control |
| `TriggerMcpServer` | daemon-호스팅 HTTP(loopback+토큰) MCP: register/list/cancel/inspect | control |

신규 `src/agent/intraday/records.py` 확장: `WakeKind`에 `"agent_trigger"` 추가.

## 2. 데이터 모델

```python
# src/agent/triggers/models.py
class TriggerSpec(BaseModel):
    id: str                       # slug, 고유
    thesis: str                   # 왜 이 트리거 (wake 프롬프트에 주입)
    created: datetime
    expires: datetime             # TTL 필수 (FR-9)
    cadence: Literal["hourly", "daily"]   # hourly floor (R4)
    sources: list[SourceRef]      # 선언 데이터 소스 (FR-4)
    primary_symbol: str | None    # WakeEvent.symbol 매핑용 (없으면 "MACRO")
    # predicate.py는 별 파일(본문은 모델에 안 실음)

class SourceRef(BaseModel):       # 카탈로그 항목 (R1 승인 + critic#2 정정)
    kind: Literal["signal", "webfetch"]   # websearch는 후속(검색 API 필요)
    # signal: name ∈ {macro, movers, earnings, holdings, sentiment} [+ params] → collector.collect
    # webfetch: url (allowlist 도메인 검증) → daemon httpx GET (CLI 툴 아님)
    ...

class Verdict(BaseModel):         # predicate 반환 / stdout 계약
    fire: bool
    why: str = ""                 # 길이 cap

class TriggerState(BaseModel):    # state.json (daemon 전용, agent 안 씀)
    last_run: datetime | None
    last_verdict: Verdict | None
    fired_count: int = 0
    last_fired: datetime | None
    consecutive_errors: int = 0
    disabled: bool = False        # 연속에러/만료 시 true
```

저장 레이아웃: `workspace/triggers/<id>/{trigger.md, predicate.py, state.json}`.
`trigger.md` = frontmatter(spec) + 본문(agent 메모). spec ↔ trigger.md round-trip = **PBT-02 대상**.

## 3. 핵심 인터페이스 (메서드 수준)

```python
class TriggerStore:
    def register(self, spec: TriggerSpec, predicate_src: str) -> TriggerSpec   # 검증+AST스크린+저장
    def list(self) -> list[TriggerSummary]
    def inspect(self, id: str) -> TriggerDetail                                # spec+state+최근 verdict
    def cancel(self, id: str) -> None
    def load_predicate(self, id: str) -> str
    def update_state(self, id: str, **changes) -> None                         # daemon 전용

class AstScreen:
    def check(self, predicate_src: str) -> list[Violation]                     # 비면 통과

class BrokeredFetcher:
    def build_ctx(self, sources: list[SourceRef]) -> dict                      # ctx.json dict (net은 여기서만)

class SandboxRunner:
    def run(self, predicate_src: str, ctx: dict, *, timeout: float) -> Verdict # Docker, fail-closed
    # 에러/타임아웃/파싱실패 → Verdict(fire=False) + 예외 분류

class TriggerEvaluator:
    def tick(self) -> None         # 스케줄러 진입점(트리거별 cadence 도래분 평가)
    # fire → rate-limit 통과 시 _emit_wake(spec, verdict)
```

## 4. 의존 그래프 (런타임)

```
TriggerMcpServer ──▶ TriggerStore ──▶ AstScreen
                                  └──▶ models
TriggerEvaluator ──▶ TriggerStore
                 ──▶ BrokeredFetcher ──▶ signals.collector / httpx-webfetch(allowlist)   [websearch 후속]
                 ──▶ SandboxRunner ──▶ Docker (execution plane)
                 ──▶ SteeringState (run_state) ──▶ gating(paused/entries_halted) [critic#3 안전 필수]
                 ──▶ (wake sink) ──▶ ReconcileWorker.trigger(kind="agent_trigger") ──▶ TurnCoordinator
```

## 5. 통합 지점 (기존 코드)

- **WakeEvent / wake 경로** (`src/agent/intraday/wake.py`, `records.py`): TriggerEvaluator가 발화 시
  `WakeEvent(kind="agent_trigger", symbol=spec.primary_symbol or "MACRO", reason=verdict.why,
  payload={"trigger_id":..., "thesis":...}, entry_inducing=True)` 생성.
  - **레인 (FR-7) — coalesce 아님, 경쟁임 (critic 정정)**: `ReconcileWorker.trigger`는 `_pending[kind]`를
    kind별로 덮어쓰므로 F88은 **별도 kind 레인 `"agent_trigger"`** 사용(WakeDetector `"wake"` 레인
    클로버 방지 — `turns.py:236-251` 확인). 단 두 레인은 **같은 우선순위 tier**에서 `reconcile_turn`의
    단일 `_turn_lock`을 경쟁(`turns.py:199`); 한쪽이 락 점유 시 다른 쪽은 자기 timeout 후
    `("timeout", None)`로 **조용히 드롭**(`_fire`에서 pending 이미 pop). 즉 **레인 간 coalesce는 없음**
    (coalesce는 한 레인 내에서만). → agent_trigger에 의도적 timeout 설정, head-of-line 비용 문서화.
    한 tick에 여러 트리거 fire 시는 F88 자체 버퍼로 한 WakeEvent 리스트에 모아 한 turn으로 전달.
  - **gating — 자동 상속 안 됨, 명시 의존 필요 (critic HIGH-safety 정정)**: WakeDetector는 paused/
    entries_halted를 **자기가** 막음(`wake.py:65-72`); gate.py는 halt를 안 막음(`gate.py:7-8`). F88
    `TriggerEvaluator`는 별 컴포넌트/잡이므로 **`SteeringState`를 명시 의존으로 주입받아** `_emit_wake`
    전에 wake.py와 동일 게이팅(paused→전부 드롭, entries_halted→entry_inducing 드롭)을 **직접 적용**해야
    함. 누락 시 halt 중 macro 트리거가 BUY 유발 → gate가 통과시켜 halt 우회. (§4 의존 그래프 반영)
- **wake turn 실행 (`orchestrator.run_wake`) — 재사용 아님, macro 경로 신규 (critic 정정)**: 현
  `run_wake`는 `reasons=[e.reason ...]`만 추출하고(`orchestrator.py:646`) `payload`/thesis를 버림.
  `wake_prompt`는 *"명시된 심볼만 확인, thesis 다시 읽지 마"*(`prompts.py:172-173`)라 macro 트리거와
  정반대. → `run_wake`/`wake_prompt`에 **macro 분기(신규 param + 조건 프롬프트)** 추가해 thesis/why를
  주입하고 포트폴리오 레벨 재평가를 허용. 결정은 **기존 gate 불변**(FR-8, `gate.py:33-49` 확인).
- **daemon 배선** (`src/trading/modes/agent.py`): steering 활성 시 TriggerEvaluator를 스케줄러 잡으로
  등록(WakeDetector 5s 옆, 단 hourly tick), TriggerMcpServer 기동.
- **agent 세션 (`src/agent/session.py`) — MCP는 신규 구축, "배선" 아님 (critic HIGH 정정)**: 현
  `_build_command`(`session.py:190-204`)에 `--mcp-config` 없음, allowed_tools는 고정 튜플 2개
  (`session.py:73-89`, 턴별 전환 없음), `scrub_agent_env`(`session.py:213`)가 토큰 스크럽. U5는 신규로
  (a)Python HTTP-MCP 서버 (b)workspace별 `.mcp.json` + `--mcp-config` 플럼빙 (c)triggers 토큰
  스크럽 화이트리스트 (d)턴별 allowlist param(현 고정 튜플 → 파라미터화)을 만들어야 함. register/cancel은
  full-tool 턴, list/inspect는 read-only 턴 — normal 모드 src 불가시(F39)는 불변.
- **brokered fetch 소스 (`src/signals/collector.py`) — web은 httpx, websearch 후속 (critic HIGH 정정)**:
  `signal` SourceRef = 기존 `SignalCollector.collect` 직접 호출(실호출 가능). `webfetch` SourceRef =
  daemon이 **httpx로 allowlist 도메인 GET**(WebFetch CLI 툴 아님). 일반 `websearch`(검색 API+키)는
  **첫 컷에서 제외, 후속**. predicate는 어느 경우든 net 0(daemon이 대신 fetch → ctx.json).

## 6. 보안 경계 (Security Baseline 매핑 재확인)

- **execution plane 격리(SECURITY-06/07/09)**: SandboxRunner만 untrusted 코드 실행. src 미마운트
  ·net=none·ro·cap-drop·non-root·시크릿 제거 env. predicate.py + ctx.json만 ro 마운트.
- **입력 검증(SECURITY-05)**: TriggerStore.register가 spec 스키마 + AstScreen + predicate 크기 cap.
- **안전 역직렬화(SECURITY-13)**: spec/ctx는 pydantic 스키마 역직렬화만(임의 객체 X); verdict는
  fire∈{bool} 강제 파싱.
- **fail-closed(SECURITY-15)**: SandboxRunner 에러 → fire=False; evaluator tick 예외는 잡아서
  스케줄러 보호(NFR), 연속에러 누적.
- **로그 무결성(SECURITY-14)**: 등록/평가/발화는 기존 audit/log로(append). 컨테이너는 audit 경로
  쓰기 권한 0.
- **공급망(SECURITY-10)**: Docker 베이스 이미지 다이제스트 핀(Infra Design에서 확정), `latest` 금지.

## 7. Units 매핑 (Units Generation 입력)

- U1=TriggerStore+models+AstScreen / U2=SandboxRunner / U3=BrokeredFetcher /
  U4=TriggerEvaluator+wake 통합+lifecycle / U5=TriggerMcpServer+session/daemon 배선.

## 8. 미해결(Construction Functional/NFR/Infra Design에서 확정)
- ctx 정확 스키마 & `should_fire(ctx)` 계약, AST 차단 목록 구체화.
- TTL 기본·상한, 최대 활성 수, rate-limit 임계, 연속에러 임계 수치.
- Docker 베이스 이미지·핀, webfetch allowlist 설정 위치(settings.yaml `triggers:` 블록 제안).
- MCP 토큰 발급/보관, `.mcp.json` 정확 포맷, HTTP 포트.

## 9. Critic Review 반영 (2026-06-16, 격리 서브에이전트 + 코드 교차확인)

7건 모두 실제 코드로 확인·유효. 반영 결과:

| # | 심각도 | 지적 | 반영 |
|---|--------|------|------|
| 1 | HIGH | MCP가 session.py에 없음 — "배선" 아닌 신규 구축 | §5 정정 + U5 재범위(아래 §10). `--mcp-config`/`.mcp.json`/토큰 스크럽 예외/턴별 allowlist 신규. |
| 2 | HIGH | daemon이 WebSearch/WebFetch(CLI 툴) 호출 불가 | **UAQ 결정**: signal=collector 직접, webfetch=httpx allowlist GET, websearch=후속 제외. §1/§2/§5 반영. |
| 3 | MED(안전) | gating 자동 상속 안 됨 — evaluator가 run_state 직접 안 읽으면 halt 우회 | §5 gating 정정 + §4 그래프에 SteeringState 의존 추가. **U4 필수 안전요건**. |
| 4 | MED | agent_trigger는 wake와 coalesce 아닌 경쟁(timeout 시 조용히 드롭) | §5 레인 정정. 의도적 timeout + head-of-line 문서화. |
| 5 | MED(인프라) | Docker-in-prod 미검증(systemd --user 소켓), 하니스는 full-source 마운트(샌드박스 정반대) | §10 + Infra Design 필수: 소켓 접근 명시 검증(SupplementaryGroups=docker/rootless) + 부팅 프로브로 "docker 불가" 큰 소리 실패(조용한 fail-closed 금지). |
| 6 | MED | run_wake는 reason만 주입, thesis 버림; 프롬프트가 "심볼만 보라" | §5 정정. run_wake/wake_prompt에 macro 분기 신규. |
| 7 | LOW | agent가 normal모드 src 불가시(F39)라 ctx 스키마 알 길 없음 | MCP `trigger.register` 툴 description + workspace-readable `ctx-schema.md`(agent가 읽을 수 있는 경로)를 ctx 계약 SSOT로. predicate 출력은 Verdict로 검증 후 에러 카운트. |

**정정된 내 오판**: WakeEvent.symbol엔 validator **없음**(`records.py:118` plain str) → "MACRO" placeholder 문제없음. 실제 필요 변경은 `WakeKind` Literal(`records.py:25`)에 `"agent_trigger"` 추가 + `kind ==` 분기 사이트(`wake.py:100` 등) grep 감사.

## 10. Critic 반영 후 Units 범위 조정 (Units Generation 입력)

- **U1** TriggerStore+models+AstScreen — 변동 없음. `WakeKind` Literal 편집 포함.
- **U2** SandboxRunner — **+ docker 가용성 부팅 프로브(loud fail)**. 하니스 재사용 가치 낮음 인지.
- **U3** BrokeredFetcher — signal(collector) + **webfetch(httpx allowlist)**; websearch 제외.
- **U4** TriggerEvaluator — **+ SteeringState 의존·gating 미러(안전 필수)** + agent_trigger 레인 timeout + run_wake macro 분기(orchestrator/prompts 수정 포함).
- **U5** TriggerMcpServer — **신규 구축으로 재범위**: HTTP-MCP 서버 + `_build_command` `--mcp-config` + 토큰 스크럽 예외 + 턴별 allowlist 파라미터화 + `ctx-schema.md` 발행.
- **Infra Design(U2/U5)**: systemd --user docker 소켓 접근 검증, 이미지 핀.
