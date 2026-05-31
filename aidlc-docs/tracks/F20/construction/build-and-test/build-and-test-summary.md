# F20 Build and Test Summary

> 모든 빌드·테스트는 이미 Code Generation 단계에서 실행 완료. 이 문서는 결과를 종합한다.

## Build Status

| 항목 | 결과 |
|------|------|
| **Build Tool** | bun (TypeScript, turbo typecheck) |
| **Typecheck** | ✅ 19 packages, all pass |
| **Dependencies** | 신규 의존성 없음 (bun 내장 `fetch`, zod·fast-check 기존) |

## Test Execution Summary

### Unit Tests

| 파일 | 테스트 | Pass | Fail |
|------|--------|------|------|
| `alpaca-data.test.ts` (신규) | 24 | **24** | 0 |
| `steer-handler.test.ts` (기존) | 13 | 13 | 0 |
| `filedrop.test.ts` (기존) | 18 | 18 | 0 |
| `parser.test.ts` (기존) | 21 | 21 | 0 |
| `launcher.test.ts` (기존) | 5 | 5 | 0 |
| `launcher-f14.test.ts` (기존) | 6 | 6 | 0 |
| `contract.test.ts` (기존) | 5 | 5 | 0 |
| **Total** | **92** | **92** | **0** |

### Unit Test Coverage (신규 `alpaca-data.test.ts`)

| 카테고리 | 설명 | 건수 |
|----------|------|------|
| HTTP 오류 코드 | 401/403/404/429/500/network/timeout → 적절한 오류 메시지 | 7 |
| 200 응답 포맷 | Account·Positions·Orders·Clock·Snapshot·Bars·Trade → markdown 검증 | 7 |
| SECURITY-12 | auth headers 응답에 미포함 | 1 |
| PBT-P1 | formatTable 행 수 invariant (0/1/25행) | 1 |
| PBT-P2 | formatBullets key:value invariant (null→"-", 중첩 객체) | 1 |
| PBT-P3 | formatResponse 모든 경로 (null/[]/{}/[items]) | 1 |
| PBT-P4 | 동일 파라미터 → 동일 결과 (round-trip) | 1 |
| PBT-P5 | HTTP 모든 status code에서 throw 없음 (200~503) | 1 |
| PBT-P6 | buildUrl 멱등성 (동일 파라미터 → 동일 결과) | 1 |
| Bar mapping | t→time, o→open 등 Alpaca raw → readable | 1 |
| Empty object | formatBullets(빈 객체) → "(empty)" | 1 |
| BR-4 field selection | `getOrders`에서 `extra_ignored` 필드 제외 확인 | 1 |
| **Total** | | **24** |

### Integration Tests

**N/A** — F20은 단일 유닛(TS 인프로세스). 데몬·FileDrop·기존 도구와의 통합점 없음 (critic H1/M2 적용 완료). 실 Alpaca API smoke test는 worktree에서 `ALPACA_API_KEY` 주입 후 수동 실행 가능.

### Performance Tests

**N/A** — 로컬 MCP 도구. Alpaca API 레이트 제한은 IEX 기본값, HTTP timeout 10s 적용 완료.

### Security Tests

**Design-time 적용** — 규칙은 code review 단계에서 검증 완료:

| 규칙 | 상태 |
|------|------|
| SECURITY-05 (Input Validation) | ✅ Zod schema → MCP SDK 자동 검증 |
| SECURITY-09 (Hardening) | ✅ 오류 응답에 스택 트레이스·내부 경로 미포함 |
| SECURITY-11 (Secure Design) | ✅ 읽기/쓰기 분리 (TS=read, Python=write) |
| SECURITY-12 (Credential Management) | ✅ env-only, auth headers 응답 미포함, paper endpoint |
| SECURITY-15 (Exception Handling) | ✅ 모든 오류 path가 string 반환, throw 없음 |

## How to Verify (Manual Smoke Test)

```bash
# In worktree
cd .claude/worktrees/F20/operator-console/cli

# Set paper trading keys
export ALPACA_API_KEY=PK...
export ALPACA_API_SECRET=...
export ALPACA_PAPER=true
export STEERING_DIR=/tmp/steering
export STEERING_OPERATOR_TOKEN=test-token

# Start MCP server with a one-shot tool call
echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_market_clock","arguments":{}},"id":1}' \
  | bun run ../../operator-console/src/mcp-server.ts 2>/dev/null | head -1
# Expected: {"content":[{"type":"text","text":"- timestamp: ...\n- is_open: ..."}]}
```

## Overall Status

| 항목 | 결과 |
|------|------|
| **Typecheck** | ✅ PASS |
| **Unit Tests** | ✅ 92/92 PASS |
| **Regression** | ✅ 0 failures (기존 68개 + 신규 24개) |
| **PBT Compliance** | ✅ P1-P6 verified |
| **Security Compliance** | ✅ 5 applicable rules, all compliant |
| **Ready** | ✅ |
