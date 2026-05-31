# F20 Application Design — Component Dependencies

## Dependency Matrix

|  | `alpaca-data.ts` | `mcp-server.ts` | opencode config | docker-compose | daemon |
|--|:--:|:--:|:--:|:--:|:--:|
| **`alpaca-data.ts`** | — | imported by | env vars from | env vars from | — |
| **`mcp-server.ts`** | imports | — | MCP tools listed | — | — (reads only) |
| **opencode config** | — | — | — | — | — |
| **docker-compose** | — | — | — | — | — |
| **daemon** | — | — | — | — | — |

## 통신 패턴

```
┌──────────────────────────────────────────────────┐
│ operator-console (bun process)                   │
│                                                  │
│  mcp-server.ts                                   │
│  ┌──────────────────────────────┐                │
│  │ registerTool("get_...") x16  │                │
│  │   ↓ (async call)             │                │
│  │ AlpacaDataClient             │                │
│  │   ├─ getAccountInfo()        │                │
│  │   ├─ getStockLatestTrade()   │                │
│  │   └─ ... (14 more)           │                │
│  └──────────┬───────────────────┘                │
│             │ bun fetch (HTTPS)                   │
└─────────────┼────────────────────────────────────┘
              │
    ┌─────────┴──────────┐
    │                    │
    ▼                    ▼
┌──────────────┐  ┌──────────────────┐
│ Alpaca       │  │ Alpaca           │
│ Trading API  │  │ Data API         │
│ paper-api.   │  │ data.alpaca.     │
│ alpaca.      │  │ markets          │
│ markets      │  │                  │
│ (9 tools)    │  │ (7 tools)        │
└──────────────┘  └──────────────────┘
```

**주요 특성**:
- **No daemon dependency**: 읽기는 콘솔에서 Alpaca API로 직접. 데몬 프로세스·FileDrop channel·snapshot.json 모두 영향 없음.
- **Stateless**: `AlpacaDataClient`는 API 키만 보유. 세션·캐시·커넥션 풀 없음.
- **Single direction**: 콘솔→Alpaca (아웃바운드 HTTPS only). 인바운드 연결 없음.
- **기존 경로 보존**: `steer_read`(snapshot/monitor), F9 structured tools, `steer` 명령어 경로 모두 그대로 유지.

## 데이터 흐름

```
User: "MSFT 현재가?"
  → opencode AI: calls tool get_stock_latest_trade({symbol_or_symbols: "MSFT"})
    → mcp-server.ts: txt(await client.getStockLatestTrade("MSFT"))
      → alpaca-data.ts: GET data.alpaca.markets/v2/stocks/MSFT/trades/latest
        ← Alpaca: { symbol: "MSFT", trade: { t: "...", p: 395.21, s: 100, x: "Q" } }
      → formatTable: | MSFT | $395.21 | 100 | Q | 2026-05-31T12:00:00Z |
    ← mcp-server.ts: { content: [{ type: "text", text: "..." }] }
  → opencode AI: "MSFT last traded at $395.21 on NASDAQ at 12:00 PM ET."
```

## Submodule Dependency (opencode config)

```
operator-console/cli/ (submodule, feat/F20 branch)
├── opencode.json                         ← 16 permission keys + env vars
└── .opencode/opencode.jsonc              ← same (fork canonical)
```

- **Parent gitlink**: merge 시점까지 commit 금지 (concurrent-tracks rule)
- **Submodule merge**: feat/F20 → submodule main → push → parent gitlink commit
