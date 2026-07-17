# F83 — Component Dependency

## 의존 방향 (패키지 내부)
```
C4 Gate ──uses──> C1 Catalog ──refs──> C2 Schemas
   │                                      ▲
   └──uses──> C3 SafeRead ────────────────┘ (parse 시 schema 사용)

C6 Drift Tests ──validates──> C1/C2/C3 (fixture·실파일)
```
- 단방향. C2(스키마)가 최하부(의존 없음). C3(안전읽기)은 zod만 의존. C1(카탈로그)이 C2 참조.
  C4(게이트)가 C1+C3 결합. 순환 없음.

## 소비측 의존 (패키지 경계 넘음)
```
@tui-trading/core (C5 Adapter) ──workspace:*──> @autostock/artifacts (C4 Gate)
```
- TUI만 신규 의존 추가. **viz-shell·mobile·Python producer는 의존 추가 없음**(NFR-1/2).
- viz-shell은 미래에 동일 게이트로 자체 코드 교체(vibeshell rebase 후, 후속 트랙).

## 빌드 배선
- `packages/artifacts/package.json`: `name:"@autostock/artifacts"`, `type:"module"`,
  `main:"src/index.ts"`, deps `{"zod":"catalog:"}`, devDeps `{fast-check, @types/bun}`.
- `tsconfig.json`: `extends:"@tsconfig/bun/tsconfig.json"`.
- 테스트: `bun test`(opencode 표준) + fast-check.
- `@tui-trading/core/package.json`에 `"@autostock/artifacts":"workspace:*"` 추가.

## 동시 트랙 영향
- **F79(모바일)**: mobile은 steer_read(Python) 경유라 이 패키지 무관. 단 모바일이 향후
  카탈로그를 쓸 여지(범위 외).
- **F80/F82(intraday store/parquet)**: 산출물 *생산* 변경 가능 → 해당 산출물을 카탈로그에
  넣을 경우 스키마 대조테스트가 drift를 잡음. 초기 엔트리는 TUI 소비분 위주라 직접 충돌 적음.
- **`@tui-trading/core` 동시 편집 트랙**: 머지 시 확인 필요(현재 미식별).

## 데이터 플로우 (런타임, TUI 예시)
```
데몬(무변경) ──writes──> steering/snapshot.json
TUI poll() ──readArtifact('snapshot', roots)──> Gate
   Gate: getEntry → join(steeringDir, "snapshot.json") → readJsonFileSync → SnapshotSchema.parse
   → Snapshot | null ──> TUI signal(contentSig 정책 보존)
```
