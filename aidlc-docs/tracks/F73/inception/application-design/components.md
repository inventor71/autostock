# F73 — Components

`viz-shell/` 단일 Next.js(App Router) 앱. 내부 6개 컴포넌트로 구획한다.
(상세 비즈니스 룰·UI 레이아웃은 Functional Design에서.)

## C1. Paths — 경로 해석·화이트리스트 (`src/server/data/paths.ts`)
- **책임**: repo 루트 해석(`AUTOSTOCK_ROOT` env 우선, 기본 `viz-shell/`의 상위), 읽기
  대상 절대경로의 **사전 정의 화이트리스트** 제공: `snapshotPath`, `equityPath`,
  `positionsDir`. 임의 경로 입력을 받는 API는 만들지 않는다(SECURITY-05 — path
  traversal의 구조적 차단).
- **인터페이스**: 상수형 getter만. 입력 없음.

## C2. SafeRead — 표면별 안전 읽기 (`src/server/data/safe-read.ts`)
- **책임**: 생산자 쓰기 방식에 맞춘 3가지 읽기 전략 (requirements FR-2):
  - `readJsonFile` — snapshot용 (생산자 원자적 → 단순 read + zod parse)
  - `tailJsonl` — equity용 (append-only → 완전한 라인만 파싱, torn-line 무시)
  - `readFileStable` — positions .md용 (비원자 생산자 → stat-stable: 읽기 전후
    mtime/size 비교, 변동 시 재시도 상한 N회)
- **특성**: 순수 함수(fs 주입 가능), **PBT 대상** (임의 절단 입력 라운드트립).

## C3. Schemas — zod 미러 스키마 (`src/server/data/schemas.ts`)
- **책임**: `SnapshotSchema`, `EquityRecordSchema` — Python 산출물의 TS 미러
  (Python pydantic이 authoritative; 미러는 관용적 파싱 — 미지 필드 passthrough).
  positions thesis는 **opaque string** (스키마 파싱 안 함).
- **특성**: parse-don't-validate. **PBT 대상** (parse→serialize 불변).

## C4. PortfolioRouter — 읽기 전용 tRPC 라우터 (`src/server/routers/portfolio.ts`)
- **책임**: MVP 데이터 표면 노출. 모든 입력 zod 검증. symbol 인자는 실재
  포지션 목록 대조(화이트리스트) — 경로 조합에 사용자 입력 직결 금지.
- **확장 계약**: 후속 표면(decisions/trades/screening 등) = 라우터 파일 1개 추가
  + `root.ts` 1줄. 스크리닝은 F72 계약 재사용.

## C5. ChatEngine — 뷰 생성 엔진 (`src/server/chat/`)
- **책임**: `/api/chat` 스트림 엔드포인트 + Claude Code SDK 래퍼 + **경계 콜백**.
  - `claude-runner.ts` — SDK `query()` 호출. 옵션: cwd=`viz-shell/`,
    `permissionMode: "default"`, Bash/WebFetch류 도구 차단, `canUseTool` = C5b.
    스티어링 토큰류 env 키를 SDK 자식 프로세스 env에서 **제거** 후 스폰 (NFR-1).
  - `boundary.ts` (**C5b, 보안 핵심**) — 모든 도구 호출 검사:
    Write/Edit → `path.resolve()` 후 `viz-shell/src/generated/` 밖이면 **deny(사유 반환)**;
    Read/Glob/Grep → `viz-shell/` 내부만 허용 (workspace/·steering/ 직접 읽기 금지 —
    thesis 본문 경유 prompt injection 벡터 차단, 데이터 접근은 tRPC 경유 원칙 유지);
    그 외 도구 → deny. 거부 시 스트림에 `boundary-denied` 이벤트 발행.
  - `session-store.ts` — **명시적 단일 세션**: sessionId 1개를 파일로 영속,
    메시지마다 `resume`, "New chat" 시 폐기·재생성.
- **스트림 계약**: `text-delta` + `tool-activity`(요약 라인) + `boundary-denied`.

## C6. ShellUI — 대시보드 셸 (`src/app/`, `src/components/`)
- **책임**:
  - `page.tsx` — 대시보드 골격: 채팅 패널 + 생성 뷰 영역 + 시드 기본 뷰 1개
  - `chat-panel.tsx` — useChat 기반; tool-activity/boundary-denied 이벤트 렌더
  - `view-host.tsx` — `generated/` **자동 레지스트리** (webpack `require.context`
    글롭 임포트, 에이전트는 컴포넌트 파일 1개만 작성) + per-view lazy-load +
    **ErrorBoundary** (깨진 생성물 격리)
  - `generated/` — 에이전트 전용 쓰기 영역. 시드 예제 `_example.tsx` 포함
    (생성 뷰가 따라할 모범: tRPC 훅 사용법, default export 규약)
  - `default-views/portfolio-summary.tsx` — 시드 기본 뷰 (스냅샷 요약 카드)
