# F83 — Components

신규 패키지 `@autostock/artifacts` (`operator-console/cli/packages/artifacts/`) 내부 구획.

## C1. Catalog (`src/catalog.ts`)
- 모든 데몬 산출물을 엔트리로 등록. **경로 리터럴의 유일한 거처**(FR-1).
- 엔트리: `{ id, base: 'steering'|'workspace', path, read: 'atomic'|'tail'|'stat-stable', schema, fixture }`.
- `read`가 읽기전략을 결정(소비자는 모름). md 산출물(thesis 등)은 `read:'stat-stable'` + 디렉토리형(파일명 파라미터).
- 신규 지표 추가 = 엔트리 1개(+fixture).

## C2. Schemas (`src/schemas.ts`)
- zod 미러. 전부 `.passthrough()`/loose — producer 필드 추가에 견고(NFR-6).
- 초기 대상(TUI 소비분): snapshot(account/positions/open_orders/recent_fills/round_trip),
  health(overall/dimensions), monitor(current_turn/queued/turns/decisions/...), turns(turn_id/
  cost_usd/tokens/...), human_directives, thesis(opaque md). + FR-6 실증 엔트리 1개.
- `export type` (zod infer)로 소비자 타입 일원화. TUI `types.ts` 대체 대상.

## C3. SafeRead (`src/safe-read.ts`)
- viz-shell code-review 반영판 이식(복제, viz-shell 무의존):
  - `readJsonFile` (atomic): ENOENT/파싱실패 → null + warn dedupe.
  - `tailJsonl` (tail): 끝에서 청크 역방향, torn-line 폐기, **bytesRead 반영**, 라인 skip 카운트.
  - `readFileStable` (stat-stable): stat→read→stat 재시도 + stale 플래그.
- fail-honest: throw 금지. 순수 함수 → PBT 대상.

## C4. Gate (`src/gate.ts`)
- Catalog + SafeRead 결합. 소비자 단일 진입점:
  - `readArtifact(id, roots)` — atomic 엔트리 → 검증된 객체 | null.
  - `tailArtifact(id, roots, opts?)` — tail 엔트리 → 검증된 배열.
  - `readMarkdownArtifact(id, roots, name)` — stat-stable md → {content, stale} | null (name 검증).
- `roots: { steeringDir, workspaceDir }` 주입. 엔트리 `base`로 루트 선택 → path 결합 → 전략 dispatch → schema.parse.

## C5. TUI Adapter (소비측 — `@tui-trading/core` 편집, 패키지 아님)
- 5훅의 파일읽기 부분만 게이트로 교체(매핑표는 application-design.md). signal/contentSig/
  freshness/correlateTurnId 등 reactive 정책 보존.
- `@autostock/artifacts` 의존 추가(`workspace:*`). `types.ts` → 스키마 재export.

## C6. Drift Tests (`tests/`)
- 엔트리별 `schema.parse(fixture)` 통과 + 가능 시 리포 실파일 parse(존재 시).
- PBT(fast-check): tailJsonl 임의 바이트 절단 무crash, 스키마 직렬화 라운드트립.
- 신규 엔트리 fixture 필수 규약(테스트가 강제).
