# F73 viz-shell — Code Generation Plan (단일 유닛)

> **이 문서가 Code Generation의 단일 진실 소스.** 각 step 완료 즉시 [x] 갱신 (같은
> 인터랙션에서). 설계 근거: `../viz-shell/functional-design/` 4문서 +
> `../../inception/application-design/` 5문서.

## 유닛 컨텍스트
- **유닛**: viz-shell (단일 유닛 — Units Generation 스킵)
- **코드 위치**: `<repo-root>/viz-shell/` (신규 디렉토리; aidlc-docs/ 금지)
- **요구 추적**: FR-1(읽기 라우터)~FR-6(뷰 영속), NFR-1~7 — User Stories 스킵이므로 FR 매핑
- **의존**: Python 데몬 산출물 파일(읽기 전용, 무변경) — `steering/snapshot.json`,
  `workspace/equity.jsonl`, `workspace/positions/*.md`
- **브랜치/worktree**: `vibeshell` 브랜치 (사용자 지정), `.claude/worktrees/F73`,
  **최신 main에서 분기** (Merge Risk Notes — 트랙 생성 시점 76ff7b6 아님)
- **머지 정책**: 장기 브랜치 — Build & Test green이어도 merge-awaiting 전환 금지

## 품질 제약 (사용자 승인 시 지침, 2026-06-13)
> "UI가 깔끔하며 버그 없으면서 사용자 request에 따라 reformable하도록"

- **깔끔**: 다크 테마 단일 디자인 토큰(Tailwind), 시드 UI는 카드/표/차트 3패턴만,
  과밀 금지. 모든 인터랙티브 요소 `data-testid` (자동화 검증 가능).
- **무버그**: 컴포넌트별 단위 테스트 + 경계 거부 테스트(보안 성공 기준 ③) + PBT
  Partial(jsonl 파서·zod 변환 라운드트립, fast-check). 깨진 생성 뷰는 ErrorBoundary로
  해당 탭만 격리 — 셸 본체 무사.
- **reformable**: 뷰 = `generated/` 단일 파일 → 채팅으로 재성형이 1급 동작.
  시드 Overview도 위젯 단위 분해(AccountCards/EquityCurve/PositionsTable 독립 파일)로
  부분 수정 용이. 스타일은 Tailwind 유틸리티(LLM이 가장 잘 다루는 형태)로 통일.

## 기술 스택 (확정)
| 항목 | 선택 | 근거 |
|---|---|---|
| 프레임워크 | Next.js 15 App Router + TypeScript | HMR=반응성 계층 (설계 핵심) |
| 스타일 | Tailwind CSS v4 (다크 기본) | LLM 생성 친화 + 일관 토큰 |
| API | tRPC v11 + @tanstack/react-query | 읽기 전용 query 라우터 |
| 스키마 | zod (passthrough 미러) | parse-don't-validate |
| 차트 | recharts | LLM 친숙도 (Functional Design 확정) |
| 채팅 | Vercel AI SDK `useChat` + 커스텀 data part | 스트림 이벤트 3종 (BR-16) |
| 에이전트 | Claude Agent SDK (`query()`) | claude CLI 구독 재사용 (Requirements 확정) |
| 마크다운 | react-markdown | ThesisDrawer (opaque 렌더) |
| 테스트 | vitest + fast-check | PBT Partial 결정 |
| dev 서버 | `127.0.0.1:3210` 고정, **webpack 모드** | BR-5; require.context는 Turbopack 비보장 → `next dev` webpack 고정(미결① 해소) |

## 생성 단계

### Phase 0 — Worktree 게이트 (blocking)
- [x] **Step 0.1**: `git fetch` 후 최신 main 확인 → `git worktree add .claude/worktrees/F73 -b vibeshell main` (base commit을 state.md에 기록, Registry 행 Worktree/Base 갱신)

### Phase 1 — 프로젝트 스캐폴드
- [x] **Step 1.1**: `viz-shell/` Next.js 스캐폴드 — package.json(dev 스크립트 `next dev -H 127.0.0.1 -p 3210`), tsconfig, Tailwind v4, 다크 테마 globals, `.gitignore`(`.cache/`, `node_modules/`, `.next/`)
- [x] **Step 1.2**: 의존성 설치 + 실버전 핀 — Claude Agent SDK `canUseTool` 시그니처를 설치된 버전 d.ts로 실측 대조(미결② 해소), AI SDK 커스텀 data part API 확인
- [x] **Step 1.3**: vitest + fast-check 셋업 (`vitest.config.ts`, `tests/` 디렉토리)

### Phase 2 — 데이터 계층 (C1·C3·C2)
- [x] **Step 2.1**: C1 `src/server/paths.ts` — repoRoot/snapshotPath/equityPath/positionsDir (화이트리스트 상수; 임의 경로 입력 부재)
- [x] **Step 2.2**: C3 `src/server/schemas.ts` — SnapshotSchema/EquityRecordSchema (passthrough, E1·E2 미러) + **실파일 표본 대조** (현재 데몬 산출물로 필드 검증)
- [x] **Step 2.3**: C2 `src/server/safe-read.ts` — readJsonFile(L2a)/tailJsonl(L2b torn-line)/readFileStable(L2c stat-stable) — fail-honest null, throw 금지
- [x] **Step 2.4**: 단위 테스트 — safe-read 3종(torn-line·stale·ENOENT 경로) + **PBT**: tailJsonl 임의 바이트 절단 무crash + 스키마 라운드트립 (fast-check)

### Phase 3 — API 계층 (C4)
- [x] **Step 3.1**: tRPC 셋업 — `src/server/trpc.ts`, `src/app/api/trpc/[trpc]/route.ts`, 클라이언트 Provider (react-query, refetchInterval 5s 기본)
- [x] **Step 3.2**: C4 `src/server/routers/portfolio.ts` — snapshot/equity({sinceDays 1..365})/listPositions/thesis({symbol}) — **전부 query, mutation 0** (BR-6), symbol 정규식+listPositions 이중 화이트리스트 (BR-7)
- [x] **Step 3.3**: 라우터 단위 테스트 — symbol 거부 케이스, sinceDays 경계, 파일 부재 fail-honest (BR-8), passthrough 미지 필드 보존 (BR-9)

### Phase 4 — 채팅 엔진 (C5, 보안 핵심)
- [x] **Step 4.1**: `src/server/chat/boundary.ts` — checkBoundary (L1: deny-by-default, WRITE→generated/만, READ→viz-shell/만, realpath 심링크 차단)
- [x] **Step 4.2**: **경계 거부 테스트** (보안 성공 기준 ③, blocking) — `../` 탈출, 절대경로, 심볼릭 링크, Bash/WebFetch deny, generated/ 내 allow — 표 형식 케이스 전수
- [x] **Step 4.3**: `src/server/chat/sanitize-env.ts` — 스티어링 토큰 실키명 grep으로 확정 후 제거 목록 작성 + 단위 테스트 (BR-4)
- [x] **Step 4.4**: `src/server/chat/session-store.ts` — `.cache/session.json` 영속 (E5, BR-14) + 테스트
- [x] **Step 4.5**: `src/server/chat/claude-runner.ts` — query() 래퍼 (L3: resume/canUseTool/sanitizeEnv/appendSystemPrompt) + 시스템 프롬프트 상수 `view-contract.ts` (BR-12: BR-10/11 영문 고지 + recharts + 경계 사전 고지)
- [x] **Step 4.6**: `src/app/api/chat/route.ts` (UIMessageStream, 이벤트 3종 E6, in-flight 409 BR-15) + `src/app/api/chat/reset/route.ts` — BR-17 구조화 로그(민감값 비기록)

### Phase 5 — 셸 UI (C6)
- [x] **Step 5.1**: `src/app/layout.tsx`(Provider+다크) + `src/app/page.tsx`(DashboardPage 골격: TopBar/ViewTabs/ChatPanel 배치, 채팅 패널 360px+접기)
- [x] **Step 5.2**: Overview 시드 위젯 — `src/components/overview/` AccountCards·EquityCurve(recharts, 7/30/90 셀렉터)·PositionsTable·ThesisDrawer(react-markdown+stale ⚠️) — 위젯별 개별 placeholder (fail-honest, BR-8)
- [x] **Step 5.3**: GeneratedViewHost — require.context 자동 레지스트리(L4, `_` 접두 제외) + lazy + ErrorBoundary("⚠️ 렌더 실패 — 채팅으로 수정 요청"+오류 요약) + Suspense
- [x] **Step 5.4**: ViewTabs/TabBar — Overview 고정 + 생성 뷰 탭(× = localStorage 숨김 BR-13), 새 뷰 자동 활성, TopBar HiddenViewsMenu 복원 드롭다운
- [x] **Step 5.5**: ChatPanel — useChat + 커스텀 파트 렌더(✎ tool-activity 회색 1줄 / ⚠️ boundary-denied 황색), ChatInput(공백 차단·4000자 soft·in-flight disabled), New chat 확인 다이얼로그
- [x] **Step 5.6**: UI 컴포넌트 단위 테스트(렌더 스모크 + hidden-views 로직) + 전 인터랙티브 요소 `data-testid` 부여 검수

### Phase 6 — 생성 뷰 규약 산출물
- [x] **Step 6.1**: `src/generated/_example.tsx` — 뷰 계약 모범(BR-11: default export + meta.title + tRPC 훅 + recharts + 5s 폴링) — 탭 비노출(`_` 접두)
- [x] **Step 6.2**: `src/generated/.gitkeep` + generated/ 전용 tsconfig 경로 alias(`@/generated`) 확인

### Phase 7 — 문서·마감
- [x] **Step 7.1**: `viz-shell/README.md` — 실행법, 127.0.0.1 고정 경고(BR-5), 보안 경계 요약, 뷰 재성형(reform) 사용법
- [x] **Step 7.2**: `aidlc-docs/tracks/F73/construction/viz-shell/code/code-summary.md` — 생성 파일 목록 + 설계 대응표
- [x] **Step 7.3**: 전체 검증 — `tsc --noEmit` + vitest 전체 green + dev 서버 기동 스모크(실데이터 렌더 확인) + Security Baseline 컴플라이언스표 갱신

## Security Baseline 게이트 (Code Gen 적용분)
- SECURITY-03(로깅): Step 4.6 BR-17 / SECURITY-04(헤더)·09(하드닝): 로컬 127.0.0.1 dev 도구 — Step 7.1에서 N/A 근거 문서화
- SECURITY-05·06·08·11·15: Phase 2~4 구현 + Step 4.2 경계 테스트가 증빙
- **비준수 발견 시 blocking** — Step 7.3 컴플라이언스표에서 최종 판정

## 완료 기준
- 전 step [x] + Step 4.2 경계 테스트 green (blocking) + Step 7.3 전체 green
- 이후 Build & Test 단계로 — **green이어도 merge-awaiting 전환 금지** (장기 브랜치 정책)
