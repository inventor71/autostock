# F73 — Component Methods (시그니처)

> 상세 비즈니스 룰은 Functional Design에서. 여기는 인터페이스 계약만.

## C1. Paths
```ts
function repoRoot(): string;                  // AUTOSTOCK_ROOT ?? resolve(vizShellDir, "..")
function snapshotPath(): string;              // <root>/steering/snapshot.json
function equityPath(): string;                // <root>/workspace/equity.jsonl
function positionsDir(): string;              // <root>/workspace/positions
```

## C2. SafeRead
```ts
function readJsonFile<T>(path: string, schema: ZodType<T>): Promise<T | null>;
// snapshot용. parse 실패 = null (fail-honest), throw 안 함

function tailJsonl<T>(path: string, schema: ZodType<T>, opts?: { maxLines?: number }): Promise<T[]>;
// equity용. 완전한('\n' 종결) 라인만. 파싱 실패 라인은 skip + 카운트 반환(로그)

function readFileStable(path: string, opts?: { retries?: number }): Promise<{ content: string; mtimeMs: number } | null>;
// positions .md용. stat→read→stat 비교, 변동 시 재시도(기본 3회), 소진 시 마지막 읽기 반환 + stale 플래그
```

## C3. Schemas
```ts
const SnapshotSchema: ZodType<Snapshot>;      // passthrough — 미지 필드 보존
const EquityRecordSchema: ZodType<EquityRecord>;
// positions thesis: 스키마 없음 (opaque string)
```

## C4. PortfolioRouter (tRPC procedures — 전부 query, mutation 없음)
```ts
portfolio.snapshot(): Snapshot | null
portfolio.equity({ sinceDays?: number }): EquityRecord[]          // zod: int, 1..365, default 30
portfolio.listPositions(): string[]                               // positionsDir 실재 파일 기준
portfolio.thesis({ symbol: string }): { symbol; markdown; mtimeMs; stale: boolean } | null
// symbol: zod regex(^[A-Z.]{1,10}$) + listPositions() 화이트리스트 대조 — 경로 조합 입력 차단
```

## C5. ChatEngine
```ts
// route.ts
POST /api/chat  body: { messages: UIMessage[] }  → UIMessageStream
// 스트림 이벤트: text-delta | tool-activity {tool, target, phase} | boundary-denied {tool, target, reason}

// claude-runner.ts
function runTurn(prompt: string, session: SessionStore, emit: (ev: StreamEvent) => void): Promise<void>;
// query() 래퍼: resume=session.id, canUseTool=checkBoundary, env=sanitizeEnv(process.env)

function sanitizeEnv(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv;
// 스티어링 토큰류 키 제거 — 단위 테스트 대상

// boundary.ts
function checkBoundary(tool: string, input: unknown): { behavior: "allow" } | { behavior: "deny"; message: string };
// 규칙: Write/Edit → resolved path가 GENERATED_DIR 이하만 allow
//       Read/Glob/Grep → resolved path가 VIZ_SHELL_DIR 이하만 allow
//       기타 도구 → deny. 모든 deny는 사유 문자열 포함 (SDK가 자가 수정 가능)
// **경계 거부 테스트의 직접 대상** (성공 기준 ③)

// session-store.ts
class SessionStore {
  get id(): string | null;
  set(id: string): void;        // 첫 턴에서 SDK가 발급한 id 저장 (파일 영속)
  reset(): void;                // New chat
}
```

## C6. ShellUI
```ts
// view-host.tsx
function discoverGeneratedViews(): Array<{ name: string; Component: LazyExoticComponent }>;
// require.context(GENERATED_DIR) 기반 — 빌드타임 글롭, dev에서 파일 추가 시 컨텍스트 무효화로 자동 픽업

// chat-panel.tsx — useChat 표준 + 커스텀 이벤트 파트 렌더 (tool-activity 요약 라인, boundary-denied ⚠️)
```
