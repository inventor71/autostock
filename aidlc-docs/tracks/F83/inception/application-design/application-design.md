# F83 — Application Design (통합)

> 상세: [components.md](components.md) · [component-methods.md](component-methods.md) ·
> [component-dependency.md](component-dependency.md). 작성 2026-06-14.

## 설계 요약

신규 monorepo 패키지 **`operator-console/cli/packages/artifacts`** (`@autostock/artifacts`)
하나 + **TUI 소비측 편집**. 6컴포넌트:

| ID | 컴포넌트 | 한 줄 책임 |
|---|---|---|
| C1 | Catalog | 산출물 엔트리 레지스트리 `{id, base, path, read, schema, fixture}` — **경로 리터럴 유일 거처** |
| C2 | Schemas | zod 미러 (passthrough; producer 필드 추가 견고). TUI 자체 타입 일원화·재export |
| C3 | SafeRead | atomic / tail(torn-line+bytesRead) / stat-stable 3종 (viz-shell code-review 반영판 이식) |
| C4 | Gate | `readArtifact`/`tailArtifact`/`readMarkdownArtifact` — Catalog lookup → 읽기전략 dispatch → SafeRead → schema.parse |
| C5 | TUI Adapter | tui-trading 5훅의 **파일읽기 부분만** 게이트로 교체 (소비측, 패키지 아님) |
| C6 | Drift Tests | 엔트리 schema ↔ fixture/실파일 대조 + PBT(안전읽기 3종) |

## 핵심 구조 결정

1. **경계 = "파일 → 검증된 데이터"까지만.** TUI 훅은 단순 읽기가 아니라 solid-js
   signal + content-signature churn 방지 + freshness tick 정책이 두껍게 얹혀 있다
   (`use-health-data.ts`/`use-monitor-data.ts` 확인). 이 **reactive/폴링 정책은 TUI
   고유로 보존**하고, 카탈로그는 `readFileSync+JSON.parse+자체 캐스팅` 부분만 대체한다.
   → 동작 보존(NFR-3)의 핵심 경계이자 마이그레이션 최소 침습.
2. **루트 모델 = base + 분리 주입.** 엔트리는 `base: 'steering'|'workspace'` + 상대 `path`.
   게이트는 `roots: { steeringDir, workspaceDir }`를 주입받음 — TUI가 이미 두 디렉토리를
   분리 주입하는 현행과 1:1, 동작 보존. (단일 `AUTOSTOCK_ROOT`도 두 경로 파생으로 수용.)
3. **스키마 관용(passthrough).** producer가 필드를 추가해도 안 깨짐(NFR-6). 필수 필드
   결손만 실패. thesis 등 md는 opaque(파싱 안 함).
4. **fail-honest 정합.** 게이트는 부재/파싱실패 → null/[]. TUI 기존 "keep last good"
   (transient miss 시 마지막 값 유지)과 충돌 없음 — 게이트가 null 주면 훅이 갱신 skip.
5. **viz-shell 무접촉(NFR-1).** safe-read/schema는 vibeshell에서 직접 못 가져오므로
   **동등 재작성(복제)**. zod는 workspace catalog **4.1.8** 사용(viz-shell 4.4와 별개).
   viz-shell은 이번 트랙에서 일절 건드리지 않음.
6. **승격(B안) 호환.** 엔트리가 선언형(`{id,base,path,read,schema,fixture}`)이라, 나중에
   Python producer에서 이 카탈로그를 생성하도록 전환 가능.
7. **확장 = 단일 등록.** 신규 지표 = Catalog 엔트리 1개 + fixture 1개. 소비자는 게이트
   호출만(경로/읽기전략 모름). FR-6 실증: 미사용 표면 ≥1개(예: snapshot `open_orders` 노출
   또는 `decisions` 엔트리) 등록.

## TUI 마이그레이션 매핑 (C5 — 동작 보존)

| 훅 / 함수 | 현재 | 교체 (정책 보존) |
|---|---|---|
| `use-snapshot-data.readPositions` | `readFileSync(snapshot.json).positions` | `readArtifact('snapshot', roots)?.positions ?? {}` |
| `use-health-data.poll` | `readFileSync(health.json)`+`JSON.parse` | `readArtifact('health', roots)` — signal/contentSig/stale/freshness 그대로 |
| `use-monitor-data.poll` | `readFileSync(monitor.json)` | `readArtifact('monitor', roots)` — contentSig/폴링 1.5s 그대로 |
| `use-session-data.readJsonl(turns/human_directives)` | `readFileSync`+split+JSON.parse | `tailArtifact('turns'/'human_directives', roots)` — correlateTurnId 보존 |
| `use-thesis.readThesis` | `readFileSync(positions/<sym>.md)` | `readMarkdownArtifact('thesis', roots, sym)` (symbol 검증 포함) |

`tui-trading/src/types.ts`의 자체 타입(PositionInfo/HealthReport/MonitorData/MonitorTurn/
MonitorDecision 등)은 C2 스키마 infer로 대체·재export → 단일 정의.

## Security Baseline 컴플라이언스 (이 단계 적용분)
| 룰 | 판정 | 근거 |
|---|---|---|
| SECURITY-05 입력검증 | 설계 반영 | 경로 입력 API 부재(카탈로그 id만), symbol은 regex+실재 대조 |
| SECURITY-06 최소권한 | 설계 반영 | 읽기전용, base+path 화이트리스트 |
| SECURITY-08 접근제어 | 설계 반영 | mutation 0(순수 read 게이트) |
| SECURITY-11 시큐어설계 | 설계 반영 | fail-honest, 카탈로그 경로 외 접근 불가 |
| SECURITY-15 예외처리 | 설계 반영 | throw 없는 reader, null/[] 반환 |
| SECURITY-01/02/03/04/07/09/10/12/13/14 | N/A | 로컬 파일 읽기 라이브러리 — 네트워크/암호화/세션/로깅 표면 없음 |

## 미결 (Functional Design 이월)
- 카탈로그 초기 엔트리 **전체 목록** + 각 zod 스키마 필드(실파일 표본 대조).
- 게이트 API 정확한 시그니처 + 반환 타입(zod infer) + roots 주입 형태.
- 테스트 러너 배선(bun test + fast-check) + fixture 디렉토리 규약.
- 패키지 빌드 배선 정확한 형태(package.json `catalog:`/tsconfig extends `@tsconfig/bun`).
- FR-6 실증용 미사용 표면 엔트리 선정(open_orders vs decisions).
