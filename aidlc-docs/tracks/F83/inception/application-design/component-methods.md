# F83 — Component Methods (시그니처 계약)

> 상세 알고리즘은 Functional Design. 여기는 인터페이스 계약(가안 — Functional에서 확정).

## C1. Catalog
```ts
type ArtifactBase = "steering" | "workspace";
type ReadStrategy = "atomic" | "tail" | "stat-stable";

interface ArtifactEntry<T> {
  id: string;                 // "snapshot", "health", "turns", ...
  base: ArtifactBase;         // 루트 선택
  path: string;               // base 상대 ("snapshot.json", "turns.jsonl", "positions")
  read: ReadStrategy;
  schema: ZodType<T>;
  fixturePath: string;        // tests fixture (대조테스트 필수)
}

const CATALOG: Record<string, ArtifactEntry<unknown>>;
function getEntry(id: string): ArtifactEntry<unknown>;   // 미등록 id → throw(개발자 오류)
```

## C2. Schemas (zod, 전부 passthrough/loose)
```ts
export const SnapshotSchema: ZodType<Snapshot>;          // account/positions/open_orders/recent_fills/round_trip/run_state
export const HealthSchema: ZodType<HealthReport>;
export const MonitorSchema: ZodType<MonitorData>;
export const TurnSchema: ZodType<MonitorTurn>;           // turns.jsonl 라인
export const HumanDirectiveSchema: ZodType<...>;
// thesis: 스키마 없음(opaque md)
export type Snapshot = z.infer<typeof SnapshotSchema>;   // ... 소비자 타입 일원화
```

## C3. SafeRead (순수 함수 — PBT 대상)
```ts
function readJsonFile<T>(absPath: string, schema: ZodType<T>): Promise<T | null>;
function tailJsonl<T>(absPath: string, schema: ZodType<T>, opts?: { maxLines?: number }): Promise<T[]>;
function readFileStable(absPath: string, opts?: { retries?: number }):
  Promise<{ content: string; mtimeMs: number; stale: boolean } | null>;
```
> 동기 변형(`*Sync`)도 제공 — TUI 훅이 동기 `readFileSync` 기반이라 동작 보존 위해 동기 경로 필요.
> Functional Design에서 sync/async 표면 확정(TUI=sync, viz-shell류 미래=async).

## C4. Gate
```ts
interface Roots { steeringDir: string; workspaceDir: string }

function readArtifact<T>(id: string, roots: Roots): T | null;           // atomic
function tailArtifact<T>(id: string, roots: Roots, opts?: { maxLines?: number }): T[];  // tail
function readMarkdownArtifact(id: string, roots: Roots, name: string):
  { content: string; mtimeMs: number; stale: boolean } | null;          // stat-stable, name 검증(regex)
// 내부: getEntry(id) → base로 roots 선택 → join(path) → read 전략 dispatch → SafeRead → schema.parse
```

## C5. TUI Adapter (소비측 — 시그니처 무변, 내부만 교체)
- `readPositions(steeringDir)` → 내부에서 `readArtifact('snapshot', {steeringDir, workspaceDir})?.positions`.
  (훅 공개 시그니처/반환 보존 = 호출부 무변경. workspaceDir 주입 배선만 추가.)
- `poll()` 내부 `readFileSync+JSON.parse` → `readArtifact(...)`. signal/sig 정책 유지.

## C6. Drift Tests
```ts
// 각 엔트리: schema.parse(loadFixture(entry.fixturePath)) — throw 없어야 통과
// 실파일 존재 시: schema.parse(realFile) (best-effort, repo 상태 의존)
// PBT: fc.assert(tailJsonl 임의 절단 무crash); schema round-trip
```
