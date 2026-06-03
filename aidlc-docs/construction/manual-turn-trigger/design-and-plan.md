# F38 — 설계 + 구현 계획 (Workflow Planning + Application Design, combined/minimal)

> Track F38. requirements.md 승인(2026-06-03) 기반. Units=1(단일 유닛), 설계 minimal.
> 기존 steering 패턴 재사용이라 새 컴포넌트 없음 — 메서드/verb 추가 수준.

## A. Workflow Planning — 실행할 단계
| 단계 | 실행 | 비고 |
|------|------|------|
| User Stories | skip | 단일 운영자 명령; FR/AC로 충분 |
| Application Design | minimal (이 문서 §B) | 새 컴포넌트 없음, 기존 코디네이터/핸들러 확장 |
| Units Generation | skip | 단일 유닛 (daemon verb + console wiring) |
| Functional / NFR / Infra Design | skip | 새 데이터모델·NFR·인프라 없음; 가드는 기존 패턴 재사용 |
| Code Generation | 실행 | §C 플랜 |
| Build & Test | 실행 | §D |

## B. Application Design (minimal)

### B.1 데이터 흐름
```
운영자 (opencode 콘솔)
  └─ /research                                  [TS]
       parser.ts: lifecycle case → verb "research", args {} , confirmRequired
       → autostock_steer MCP tool (이미 ask-gated; 새 permission key 불필요)
       → file-drop command
  └─ SteeringRuntime.poll_commands (2s job)     [PY]
       → CommandBus 워커 스레드 → CommandHandler.handle → _v_research
            ├─ paused?              → emit "deferred" (turn 미실행)
            └─ turn_trigger_fn("research")
                 → TurnCoordinator.start_async(orchestrator.run_morning_research)
                      ├─ reconcile 대기 중      → "reconcile_waiting"  → emit "skipped"
                      ├─ turn_lock busy        → "busy"               → emit "skipped"
                      └─ 획득 성공 → daemon Thread 시작(run_fn) → "started" → emit "triggered"
       (워커는 즉시 반환 — turn 본 실행은 백그라운드 스레드, FR-4 논블로킹)
```

### B.2 변경 지점 (정확한 위치)
**Python (daemon)**
1. `src/agent/steering/turns.py` — `TurnCoordinator.start_async(run_fn, *, kind="manual") -> str`
   추가. 비차단 acquire(스케줄 turn과 동일한 skip-if-busy + reconcile 우선), 획득 시 daemon
   `threading.Thread`로 `run_fn` 실행 후 lock 해제. 반환 `"started"|"busy"|"reconcile_waiting"`.
   - `try_scheduled_turn`의 가드 로직과 동일(우선순위·비차단)하되, 실행을 **별 스레드로 분리**해
     호출자(=bus 워커)를 막지 않음. NFR-1(단일 세션 동시 실행 금지)은 동일 `turn_lock`로 보존.
2. `src/agent/steering/records.py` — `SteeringVerb` Literal에 `"research"` 추가; `_KIND`
   매핑(commands.py)에 `"research": "lifecycle"` 추가.
3. `src/agent/steering/commands.py` — `CommandHandler.__init__`에 `turn_trigger_fn:
   Callable[[str], str] | None = None` 주입. `_v_research` 핸들러 추가(paused 가드 → 아니면
   turn_trigger_fn 호출 → status별 emit).
4. `src/agent/steering/runtime.py` — CommandHandler 생성(line 69) 시 `turn_trigger_fn=
   self._trigger_turn` 전달. `_trigger_turn(kind)` 추가:
   `return self.coordinator.start_async(self.orchestrator.run_morning_research, kind="manual_research")`.

**TypeScript (console)**
5. `operator-console/src/schema.ts` — `SteeringVerb` union에 `"research"` 추가
   (READ_ONLY/DESTRUCTIVE 목록에는 넣지 않음).
6. `operator-console/src/parser.ts` — lifecycle `case`에 `"research"` 추가
   (`case "pause": ... case "research": return mk("research", {}, "research")`). 인자 없음,
   confirmRequired(mk 기본값) → opencode가 confirm.
7. `operator-console/src/mcp-server.ts` — `steer` 도구 설명의 LIFECYCLE/OTHER 줄에
   `/research` 한 줄 추가(운영자/agent 노출용 도움말).

### B.3 가드 일관성 (D2)
- `paused` 체크: `CommandHandler.state.run_state().paused` (스케줄 `_premarket_research`와 동일 의미).
- skip-if-busy: 동일 `TurnCoordinator.turn_lock` 비차단 acquire(스케줄과 동일).
- `market_open`: 검사 안 함(research는 프리마켓 실행 — `_premarket_research`도 미검사).
- 동시성: research는 broker를 read만(held_symbols→portfolio_provider), 스케줄 research도 이미
  bus 외 스레드에서 동일 read 수행 → 새 race 없음(스케줄 경로와 1:1).

## C. Code Generation 플랜 (체크박스)
- [x] C-1: `turns.py` `TurnCoordinator.start_async` 추가
- [x] C-2: `records.py` SteeringVerb에 `research` 추가 + contract.json 재생성
- [x] C-3: `commands.py` `_KIND["research"]` + `_v_research` + `turn_trigger_fn` 주입 파라미터
- [x] C-4: `runtime.py` `_trigger_turn` + CommandHandler 생성 시 주입
- [x] C-5: `schema.ts` SteeringVerb/ALL_VERBS/LIFECYCLE_VERBS에 `research`
- [x] C-6: `parser.ts` lifecycle case에 `research`
- [x] C-7: `mcp-server.ts` 도움말 텍스트에 `/research` (TURN 줄)
- [x] C-8: 테스트 — PY 11건(start_async 5 + _v_research 6) + TS parser 1건, 전부 통과

- [x] C-9 (FR-7 추가): 완료 푸시 이벤트 — `start_async`에 `on_done(result,error)` 훅(턴락 보유 중
  호출), `runtime._trigger_turn(kind,corr_id)`가 결정수 계산 후 `bus.submit(emit_outcome(corr_id,
  "completed"/"failed", detail))`. `_v_research`가 `cmd.id` 전달. TS 변경 불필요(이벤트 렌더 제네릭).
  테스트: start_async on_done(success/failure/lock-held) +3, runtime e2e 완료/실패 +2.

### 검증 결과 (2026-06-03)
- PY: 신규 11건 통과; 전체 steering suite **115 passed**.
- TS: `parser.test.ts` 11 pass(/research 포함), `contract.test.ts` 6 pass, `tsc --noEmit` exit 0.
- `alpaca-data.test.ts`만 ALPACA env 미설정으로 실패 — F20 라이브 데이터 테스트, F38 무관(기존/환경).
- git status: 의도한 11개 파일만 변경(stray lockfile/node_modules 없음).

## D. Build & Test
- **Python 단위 테스트** (`tests/` 기존 steering 테스트 옆에 추가):
  - T-1 `start_async`: idle → "started" + run_fn이 백그라운드에서 1회 실행(이벤트로 join 확인).
  - T-2 `start_async`: turn_lock 선점 상태 → "busy", run_fn 미실행.
  - T-3 `start_async`: reconcile_waiting>0 → "reconcile_waiting", run_fn 미실행.
  - T-4 `_v_research`: paused=True → outcome "deferred", turn_trigger_fn 미호출.
  - T-5 `_v_research`: paused=False + trigger_fn="started" → outcome "triggered" (stub fn).
  - T-6 `_v_research`: trigger_fn="busy" → outcome "skipped".
  - T-7 비차단: `_v_research`가 turn 완료를 기다리지 않고 즉시 반환(stub이 blocking이어도 핸들러 즉시 복귀).
- **TS 단위 테스트** (`operator-console/test/`): parser가 `/research` → `{verb:"research",args:{}}`.
- **typecheck**: worktree에서 `bun run typecheck`(TS), `python -m pytest`(PY) — 컨테이너/worktree 부트스트랩.

## E. 범위 밖 / 후속
- intraday/eod 트리거(`/run-turn <type>` 일반화) — 후속 트랙.
- turn 완료 동기 대기/결과 반환 — FR-4와 상충, 의도적으로 제외.
