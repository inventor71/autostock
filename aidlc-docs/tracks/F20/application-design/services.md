# F20 Application Design — Services

> F20은 단일 서비스 계층. 오케스트레이션 복잡도가 낮아 서비스 분리는 불필요.

## 서비스 계층

### S1. Alpaca Read Service (`AlpacaDataClient` → `mcp-server.ts` 도구)

**패턴**: 도구별 1:1 메서드 매핑, 서비스 오케스트레이션 없음.

**흐름**:
```
opencode MCP stdio transport
  → mcp-server.ts registerTool handler
    → zod.parse(args)                        // StdioServerTransport가 이미 실행하지만, 명시적 재검증은 안 함 (Zod schema=경계)
    → alpacaDataClient.<method>(params)       // TS 인프로세스 → Alpaca HTTPS
    → Alpaca JSON 응답 → formatTable/bullets  // 마크다운 변환
    → return { content: [{ type: "text", text }] }  // opencode에게 text 반환
```

**기존 서비스와의 관계**:

| 서비스 | 역할 | F20 영향 |
|--------|------|----------|
| `FileDrop` | 콘솔↔데몬 파일 채널 (commands/events/snapshot) | **영향 없음** — 읽기는 FileDrop 우회 |
| `handleSteerRead` | snapshot/monitor.json 읽기 | **유지** — 데몬 내부 상태(run_state, agent-trace, turns, decisions, log)는 steer_read만 제공. positions/orders/book 조회 시에는 **F20 live 도구를 우선 사용**하도록 각 도구 description에 명시. |
| `handleStructured` | F9 구조화 주문 처리 | **영향 없음** |
| `handleSteer` | 구문 분석 주문 경로 | **영향 없음** |
| 데몬 `RiskManager` | 주문 게이팅·보호 | **영향 없음** — 읽기 전용 |
| 데몬 `AlpacaBroker` | 파이썬 시세 경로 | **영향 없음** — 중복이지만 의도적 (NFR-2) |

### `steer_read` vs F20 live 도구 — 데이터 신뢰도 계층

| 데이터 카테고리 | steer_read (daemon snapshot) | F20 (live Alpaca API) | 우선 사용 |
|----------------|------------------------------|----------------------|-----------|
| **데몬 내부 상태** (run_state, agent-trace, why, locked_symbols) | ✅ 유일한 소스 | ❌ 제공 불가 | steer_read |
| **모니터 통계** (turns, decisions, log) | ✅ 유일한 소스 | ❌ 제공 불가 | steer_read |
| **포지션** | `snapshot.json` 주기적 갱신 (stale 가능) | `get_all_positions` / `get_open_position` — 실시간 | **F20** |
| **주문** | `snapshot.json` 주기적 갱신 (stale 가능) | `get_orders` — 실시간, 필터 풍부 | **F20** |
| **시세** | 보유·대기 종목만 (snapshot) | `get_stock_latest_trade` / `get_stock_snapshot` — 임의 종목, 실시간 | **F20** |
| **계좌** | `snapshot.json` 주기적 갱신 | `get_account_info` — 실시간 | **F20** |

**설계 원칙**:
- AI는 positions/orders/account/market-data 조회 시 **F20 도구를 우선 사용**해야 한다 (실시간, 더 풍부한 필드).
- `steer_read`는 데몬 내부 운영 상태(/status, /agent-trace, /why, /turns, /decisions, /log)에만 사용.
- 두 경로의 응답이 충돌하면 F20(live Alpaca)이 더 최신이므로 신뢰 — snapshot은 "up to N seconds stale"임을 도구 description에 표기.
- 각 F20 도구 description에 "live Alpaca API — fresher than daemon snapshot" 명시. `steer_read` description에 "returns daemon snapshot; for live Alpaca data use get_* tools" 추가.

## 서비스 오케스트레이션: 필요 없음

16개 도구는 각각 독립적인 Alpaca API 호출. 도구 간 의존성 없음.
도구 체이닝(예: clock 확인 → positions 조회 → snapshot)은 AI/opencode가 결정 — 서비스 계층은 관여하지 않음.

## 싱글톤 라이프사이클

```typescript
// mcp-server.ts (모듈 로드 시)
import { AlpacaDataClient } from "./alpaca-data";
const client = new AlpacaDataClient(); // fail-fast: 키 없으면 여기서 process.exit(1)
```

- `AlpacaDataClient`는 stateless (API 키만 저장, 캐시 없음, 커넥션 풀 없음)
- 싱글톤으로 충분 — 인스턴스당 리소스 공유 불필요
- `bun fetch`는 요청별로 TCP 연결을 열지만, HTTP keep-alive는 bun 런타임이 관리
