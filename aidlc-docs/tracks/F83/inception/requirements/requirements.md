# F83 — Requirements (공유 산출물 카탈로그 SSOT + 공통 read 게이트)

> Depth: standard. 작성 2026-06-14. Q1=A안, 범위=카탈로그+TUI 확정(UAQ).

## 1. 배경 / 문제

데몬(Python producer)이 `steering/`·`workspace/`에 쓰는 json/jsonl/md 산출물을 소비하는
세 표면이 **공통 게이트 없이 각자 직접 읽고 재파싱**한다:

- **TUI** (`@tui-trading/core`): 읽기 훅 5종(`use-{snapshot,health,monitor,session}-data`,
  `use-thesis`)이 `readFileSync(steeringDir/...)` **직격** + 자체 타입. torn-read 무방비.
- **viz-shell** (vibeshell 브랜치, **미머지**): `src/server/{paths,safe-read,schemas}.ts`로
  자체 zod + 안전읽기 3종. 카탈로그의 사실상 원형.
- **mobile** (F71 PWA): 데몬 `steer_read` 결정론 경로 래핑 — 파일 직접 안 읽음(Python 경유).

산출물 파일명 리터럴이 코드에 분산(예: `decisions.jsonl` 13곳), 중앙 카탈로그/스키마 부재.
→ 새 지표 추가·산출물 구조 변경 시 각 소비자가 독립 재구현·독립 파손(drift 무감지).

## 2. 목표

데몬 산출물의 **{경로 + 읽기전략 + 스키마}를 단일 소스(SSOT)** 로 묶고, 소비자가
**공통 read 게이트**를 타게 한다. **신규 지표 추가가 카탈로그 1엔트리 + 소비자 import**로
끝나게(소비자 코드 변경 0으로 노출 가능) 만든다.

## 3. 채택 설계 (UAQ 결정)

- **A안**: TS 공유 패키지(monorepo bun workspace 내, 예: `packages/artifacts`)에
  경로 카탈로그 + zod 스키마 + 안전읽기 게이트. Python producer **무변경**, CI 대조
  테스트로 정합 유지. codegen(B안)으로 **승격 가능한 구조**로 설계.
- **범위**: 공유 패키지 신설 + **TUI 5훅 마이그레이션**. viz-shell·mobile은 후속.

## 4. 기능 요구 (FR)

- **FR-1 (카탈로그 = 4튜플 단일 등록)**: 각 산출물을 `{ id, path(상대), read: atomic|tail|stat-stable, schema(zod), fixture(샘플) }`
  단일 엔트리로 등록. 신규 지표 추가 = 엔트리 1개(+픽스처 1개). 경로 리터럴은 카탈로그에만.
- **FR-2 (공통 read 게이트)**: 카탈로그 id로 읽는 단일 API
  (`readArtifact(id, root)` / `tailArtifact(id, root, {maxLines})` 등). 소비자는 경로·읽기전략을
  몰라도 됨. 루트(`steeringDir`/`workspaceDir` 또는 단일 `AUTOSTOCK_ROOT`)는 주입.
- **FR-3 (안전읽기 3종 캡슐화)**: atomic(원자 JSON), tail(append-only JSONL torn-line 폐기 +
  bytesRead 반영), stat-stable(비원자 md 재시도 + stale 플래그). viz-shell `safe-read.ts` 이식.
  fail-honest(throw 금지, 부재→null/[]).
- **FR-4 (TUI 마이그레이션, 동작 보존)**: `@tui-trading/core` 읽기 훅 5종을 카탈로그 게이트로
  교체. 화면·폴링 주기·표시 동작 회귀 없음. 자체 타입(PositionInfo 등)을 카탈로그 스키마로 대체.
- **FR-5 (drift 대조 테스트)**: 각 카탈로그 엔트리의 zod 스키마가 **실 산출물 샘플**(픽스처 +
  가능 시 리포 실파일)을 통과하는지 CI에서 검증. 불일치 = fail. 신규 엔트리는 픽스처 필수.
- **FR-6 (확장 데모)**: 카탈로그에 현재 TUI가 쓰는 산출물(snapshot/health/monitor/thesis/session)
  + 즉시 가치 있는 미사용 표면 최소 1개(예: snapshot 내 `open_orders`/`recent_fills` 또는
  `decisions.jsonl`)를 등록해 "엔트리 추가만으로 노출 가능"을 실증. (실제 새 UI는 범위 외 —
  카탈로그 등록까지만.)

## 5. 비기능 요구 (NFR)

- **NFR-1 (viz-shell 무의존 — 핵심 제약)**: 카탈로그가 viz-shell 코드/vibeshell 브랜치에
  의존하지 않고, **이번 트랙은 viz-shell을 건드리지 않는다**. viz-shell의 카탈로그 채택은
  vibeshell이 main rebase 후 진행하는 **후속 작업**. 양방향 독립.
- **NFR-2 (producer 무변경)**: Python 데몬의 산출물 *생산* 경로 무변경. 카탈로그는 순수 소비측.
- **NFR-3 (TUI 동작 보존)**: 마이그레이션 후 TUI 회귀 0. 기존 폴링 간격(snapshot 5s, monitor 1.5s
  등) 유지.
- **NFR-4 (확장성)**: 신규 산출물 노출 비용 = 카탈로그 1엔트리 + 소비자 import. 소비자별
  경로/파싱/안전읽기 재구현 0.
- **NFR-5 (drift 가시성)**: 스키마 ↔ 실 산출물 불일치가 CI fail로 드러남.
- **NFR-6 (승격 경로)**: 카탈로그 엔트리 정의를 나중에 Python에서 생성(codegen=B안)하도록
  전환 가능한 형태. 스키마 관용성(`passthrough`/`loose`)으로 producer 필드 추가에 견고.
- **NFR-7 (보안 — Security Baseline)**: 경로는 카탈로그 화이트리스트만(임의 경로 입력 API 부재).
  symbol 등 사용자 파라미터는 검증(regex + 실재 대조). 전 표면 읽기 전용.

## 6. Extension 요구

- **Security Baseline (Yes, 전체 blocking)**: 산출물 경로 화이트리스트, 경로주입 차단, 읽기전용
  보장, fail-honest. 스테이지별 N/A 판정 허용(예: 네트워크/암호화 N/A).
- **Property-Based Testing (Partial)**: 순수 함수 한정 — 안전읽기 3종(임의 바이트 절단·torn-line
  무crash) + zod 스키마 직렬화 라운드트립. fast-check.

## 7. 범위 외 (명시)

- **viz-shell 마이그레이션** — 후속(vibeshell rebase 후).
- **mobile/steer_read(Python) 카탈로그화** — 후속.
- **Python producer 정형화/codegen(B안)** — 별도(F80/F82 영역과 맞물림).
- **새 지표용 실제 UI 추가** (F73에서 논한 Tier 0~3 위젯) — 카탈로그 등록까지만, UI는 별도.
- 산출물 *생산* 로직·포맷 변경.

## 8. 성공 기준

1. `packages/artifacts`(가칭) 공유 패키지: 카탈로그 + 안전읽기 게이트 + zod 스키마, 단위/PBT 통과.
2. TUI 5훅이 카탈로그 게이트로 교체되고 기존 동작 보존(빌드+런타임 스모크).
3. drift 대조 테스트가 CI에서 동작(스키마↔샘플).
4. 카탈로그에 미사용 표면 ≥1개 등록으로 "엔트리 추가만으로 노출 가능" 실증.
5. viz-shell·Python producer 무변경(NFR-1/2).
