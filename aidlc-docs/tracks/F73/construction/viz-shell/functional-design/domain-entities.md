# F73 viz-shell — Domain Entities

> Python 산출물이 authoritative — TS 미러는 관용적(passthrough). 필드는 Code Gen에서
> 실파일 표본으로 최종 대조한다 (아래는 실파일 1차 확인 기준).

## E1. Snapshot (`steering/snapshot.json` 미러)
```ts
SnapshotSchema = z.object({
  // 핵심 사용 필드 (Overview 시드 뷰)
  equity: z.number().optional(),
  cash: z.number().optional(),
  buying_power: z.number().optional(),
  positions: z.array(z.object({
    symbol: z.string(),
    qty: z.coerce.number(),
    avg_entry_price: z.coerce.number().optional(),
    market_value: z.coerce.number().optional(),
    unrealized_pl: z.coerce.number().optional(),
  }).passthrough()).default([]),
  updated_at: z.string().optional(),    // + 데몬 SHA 등 메타
}).passthrough();
```

## E2. EquityRecord (`workspace/equity.jsonl` 라인 미러)
```ts
EquityRecordSchema = z.object({
  ts: z.string(),                        // ISO
  equity: z.number(),
  benchmark: z.record(z.number()).optional(),
}).passthrough();
```

## E3. ThesisDoc (positions/*.md — opaque)
```ts
type ThesisDoc = {
  symbol: string;
  markdown: string;      // 파싱 안 함 — 렌더만 (react-markdown)
  mtimeMs: number;
  stale: boolean;        // stat-stable 재시도 소진 시 true
};
```

## E4. GeneratedView (파일시스템이 source of truth)
```ts
type GeneratedView = {
  fileName: string;          // "pnl-by-symbol.tsx"
  title: string;             // meta.title ?? 파일명 변환
  Component: LazyExoticComponent;
};
// 영속 상태는 파일 자체. 클라이언트 부가 상태:
type ViewVisibility = string[];   // localStorage "viz-shell.hidden-views" — 숨긴 fileName 목록
```

## E5. ChatSession
```ts
type ChatSession = { id: string | null; createdAt: string };
// viz-shell/.cache/session.json (gitignore) — 단일 레코드
```

## E6. StreamEvent (chat 스트림 커스텀 파트)
```ts
type StreamEvent =
  | { type: "text-delta"; delta: string }
  | { type: "tool-activity"; tool: string; target: string }        // 상대경로 요약
  | { type: "boundary-denied"; tool: string; target: string; reason: string };
```

## 관계
- Snapshot.positions[].symbol ↔ ThesisDoc.symbol (선택적 — thesis 없는 포지션 가능,
  역도 가능: 청산 후 thesis 잔존)
- GeneratedView ↔ ViewVisibility: fileName 키 매칭 (파일 삭제 시 visibility 항목은
  무해한 고아 — 정리 불필요)
- ChatSession ↔ GeneratedView: 무관계 (세션 리셋해도 뷰 파일 잔존 — 의도된 영속성, FR-6)
