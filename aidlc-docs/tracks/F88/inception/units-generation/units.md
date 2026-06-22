# F88 Units Generation (standard)

> application-design.md §7/§10 + critic 반영 기반으로 5개 작업 단위 정식 분해.
> 단위별로 완결(설계+코드+테스트) 후 다음. 패키지: `src/agent/triggers/`.

## 의존 순서
```
U1 (store/models/AstScreen) ─┬─▶ U2 (SandboxRunner) ──┐
                             ├─▶ U3 (BrokeredFetcher) ┼─▶ U4 (Evaluator/lifecycle/wake) ─▶ U5 (MCP/wiring)
                             └────────────────────────┘
```

---

## U1 — TriggerStore & models & AstScreen
- **경계**: `triggers/models.py`(TriggerSpec/SourceRef/Verdict/TriggerState), `triggers/store.py`,
  `triggers/ast_screen.py`. `records.py` `WakeKind`에 `"agent_trigger"` 추가(+ `kind ==` 사이트 grep 감사).
- **책임**: `workspace/triggers/<id>/{trigger.md,predicate.py,state.json}` CRUD, spec↔trigger.md
  직렬화(round-trip), 스키마/크기 검증, predicate AST 정적 차단.
- **인터페이스**: `register/list/inspect/cancel/load_predicate/update_state`(daemon 전용 state).
- **PBT(02)**: spec↔trigger.md, ctx 객체↔json round-trip. **PBT(03)**: TTL/만료 판정 불변.
- **수용 기준**: 등록→로드 round-trip 동등; 만료 spec은 평가 후보 제외; AstScreen이 금지 import/호출
  거부; verdict 파싱 fire∈{bool} 강제.

## U2 — SandboxRunner (Docker 격리)
- **경계**: `triggers/sandbox.py` + 컨테이너 entrypoint + Dockerfile(triggers 전용, 베이스 핀).
- **책임**: predicate를 일회용 컨테이너에서 실행. **src 미마운트 / `--network=none` / `--read-only` /
  `--cap-drop=ALL` / non-root / `--no-new-privileges` / mem·cpu·pids 상한 / wall-clock timeout /
  시크릿 제거 env / tmpfs만 쓰기 / `--rm`**. predicate.py + ctx.json만 ro 마운트. stdout(크기 cap)→Verdict.
- **critic#5**: **docker 가용성 부팅 프로브**(소켓 접근 불가 시 큰 소리 실패 — 조용한 fail-closed 금지).
- **fail-closed(SECURITY-15)**: 에러/타임아웃/파싱실패 → `Verdict(fire=False)` + 예외 분류.
- **수용 기준(보안 테스트 필수)**: predicate가 `src/` 읽기 시도→불가(미마운트), `os.environ` 시크릿→빈손,
  네트워크 송신→불가, 무한루프→timeout kill(daemon 무영향), 정상 predicate→Verdict 회수.

## U3 — BrokeredFetcher
- **경계**: `triggers/fetch.py`.
- **책임**: 선언 SourceRef → `ctx.json` dict. `signal`=`SignalCollector.collect` 매핑;
  `webfetch`=allowlist 도메인 httpx GET(타임아웃·크기 cap·실패 fail-honest). TTL 캐시.
  **websearch 제외(후속)**.
- **수용 기준**: signal 소스가 collector 결과를 ctx에 정확 매핑; webfetch allowlist 밖 URL 거부;
  fetch 실패가 ctx에 honest하게 표기(predicate가 구분 가능).

## U4 — TriggerEvaluator & lifecycle & wake 통합
- **경계**: `triggers/evaluator.py` + `orchestrator.run_wake`/`prompts.wake_prompt` macro 분기 수정.
- **책임**: cadence 루프(hourly floor), TTL/만료 제외, rate-limit(트리거별 발화), 연속에러 자동
  비활성화. fire→`WakeEvent("agent_trigger", symbol=primary or "MACRO", reason=why,
  payload={trigger_id,thesis}, entry_inducing)`→`ReconcileWorker.trigger(kind="agent_trigger")`.
- **critic#3(안전 필수)**: `SteeringState` 의존 주입 → `_emit_wake` 전 paused/entries_halted 게이팅
  (`wake.py:65-72` 미러).
- **critic#4**: agent_trigger 레인 의도적 timeout, head-of-line/경쟁 동작 문서·테스트.
- **critic#6**: run_wake에 macro 분기 — payload thesis/why를 프롬프트 주입, 포트폴리오 재평가 허용.
- **PBT(03)**: rate-limit 카운터 단조성, 만료/비활성화 불변.
- **수용 기준**: 만료 트리거 미평가; rate-limit 초과 발화 억제; 연속에러 N회→disabled; entries_halted
  중 entry_inducing 트리거 wake 억제(halt 우회 없음); macro wake turn 프롬프트에 thesis 포함.

## U5 — TriggerMcpServer & session/daemon 배선 (신규 구축)
- **경계**: `triggers/mcp_server.py`(daemon-호스팅 HTTP), `session.py` `_build_command`/allowed_tools
  수정, daemon `agent.py` 기동, `workspace/ctx-schema.md` 발행.
- **책임(critic#1)**: loopback HTTP MCP(토큰) — `trigger.register/list/cancel/inspect`(SECURITY-05
  입력검증·인자 스키마). `--mcp-config` + workspace `.mcp.json` 생성 플럼빙. **triggers 토큰
  scrub_agent_env 화이트리스트**. 턴별 allowlist 파라미터화(register/cancel=full-tool, list/inspect=
  read-only도). **가시성 제약(FR-10)**: normal 모드 src 불가시(F39) 불변.
- **critic#7**: `ctx-schema.md`(agent가 workspace에서 읽을 수 있음) + 툴 description이 ctx 계약 SSOT.
- **수용 기준**: agent 세션이 MCP로 트리거 CRUD; 토큰 없는 접근 거부; 토큰이 agent env로 새지 않음
  (스크럽 검증); read-only 턴은 register 거부; agent가 ctx-schema.md로 predicate 작성 가능.

## Infra Design 대상 (U2/U5)
- triggers Docker 베이스 이미지 다이제스트 핀(SECURITY-10, `latest` 금지).
- prod daemon(systemd --user) docker 소켓 접근(SupplementaryGroups=docker / rootless) 검증.
- settings.yaml `triggers:` 블록(allowlist 도메인, TTL/최대수/rate-limit/연속에러 임계, cadence, MCP 포트).

## Build & Test (전 단위 후)
격리 보안 테스트(U2 수용기준), fail-closed, gating halt 우회 없음, rate-limit/TTL/비활성화,
PBT(round-trip·불변), 통합(register→eval→fire→macro wake), 라이브 스모크, post-merge-guide.
