# F88 Workflow Plan

> Requirements 승인(2026-06-16) 후 작성. 이 트랙에서 실행할 단계·깊이·순서.

## 단계 실행 계획

| 단계 | 실행 | 깊이 | 근거 |
|------|------|------|------|
| Workspace Detection | ✅ 완료 | — | brownfield, CodeKB 소비, 신규 요청 |
| Reverse Engineering | ⏭️ skip | — | CodeKB 존재로 충분 |
| Requirements Analysis | ✅ 완료 | comprehensive | 보안·코드실행 격리 핵심 |
| **User Stories** | ⏭️ **skip** | — | 단일 개발자·내부 agent 능력 확장. "사용자"=agent 자신, 다중 페르소나/UAT 없음. 요구·아키텍처 이미 락. (CLAUDE.md: 순수 백엔드/내부 능력은 skip 후보) |
| Workflow Planning | ✅ (현재) | — | 항상 실행 |
| **Application Design** | ✅ **execute** | standard | 신규 컴포넌트 다수(MCP 서버·TriggerStore·Evaluator·Sandbox runner), 컴포넌트 의존·경계·메서드 정의 필요 |
| **Units Generation** | ✅ **execute** | standard | 시스템을 5개 작업 단위로 분해(아래) |
| Construction(per-unit) | ✅ execute | — | Functional/NFR/Infra Design + Code Gen을 단위별로 |
| Build & Test | ✅ execute | — | 통합·보안·격리 테스트 필수 |

## 제안 Units (Units Generation에서 확정)

1. **U1 — TriggerStore & spec/schema**: `workspace/triggers/<id>/` 레이아웃, trigger.md/predicate.py/
   state.json 직렬화·검증, AST 스크린. (PBT round-trip 핵심)
2. **U2 — Sandbox Runner**: Docker 일회용 실행(src 미마운트·net=none·ro·cap-drop·limits·timeout·
   시크릿 제거), ctx 주입, verdict 파싱, fail-closed. docker-verify 하니스 패턴 재사용.
3. **U3 — Brokered Fetch**: 선언 데이터 소스 카탈로그(signals + WebSearch + WebFetch allowlist) →
   `ctx.json` 조립, TTL 캐시. signals collector 재사용.
4. **U4 — TriggerEvaluator & lifecycle**: cadence 루프(hourly floor), rate-limit, TTL/만료, 연속에러
   자동 비활성화, fire→`WakeEvent("agent_trigger")`, 기존 WakeDetector와 dedup/coalesce.
5. **U5 — MCP Server & wiring**: daemon-호스팅 HTTP(loopback+토큰) MCP, trigger.register/list/
   cancel/inspect, agent 세션 `.mcp.json`/allowed-tools 배선, 가시성 제약(FR-10).

### 의존 순서
```
U1(store/schema) ─┬─▶ U2(sandbox runner) ─┐
                  ├─▶ U3(brokered fetch) ──┼─▶ U4(evaluator/lifecycle) ─▶ U5(MCP/wiring)
                  └────────────────────────┘
```
U1이 기반, U2·U3 병렬 가능, U4가 통합 루프, U5가 agent 노출. 단위별로 완결(설계+코드) 후 다음.

## 단위별 적용 단계 (Construction)
- **Functional Design**: U1(스키마·직렬화·AST 규칙), U4(상태머신·dedup) — 실행. U2/U3/U5는 경량.
- **NFR Requirements/Design**: U2(격리·자원), U5(인증·rate-limit) — 보안 NFR 집중.
- **Infrastructure Design**: U2(Docker 이미지 핀·실행 환경), U5(MCP 엔드포인트) — 실행.
- **Code Generation**: 전 단위 ALWAYS.

## Build & Test 강조점
- 격리 테스트(src 접근 시도·시크릿 접근·네트워크 시도가 실제 차단되는지 — fail 케이스).
- fail-closed(에러 predicate→미발화), rate-limit·TTL·연속에러 비활성화.
- PBT(spec/ctx round-trip, 불변) + 통합(등록→평가→fire→wake) + 라이브 스모크.
- post-merge-guide (user-facing: agent 새 능력·MCP·Docker 의존·설정 키).
