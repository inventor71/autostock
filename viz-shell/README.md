# viz-shell — 읽기 전용 생성형 대시보드 사이드카 (F73)

autostock 데몬 산출물(`steering/snapshot.json`, `workspace/equity.jsonl`,
`workspace/positions/*.md`)을 **읽기 전용**으로 시각화하는 Next.js 앱.
우측 채팅 패널에서 Claude Agent SDK로 **뷰를 말로 생성/수정**하면
(`src/generated/` 단일 파일), dev 서버 HMR이 즉시 탭으로 반영한다.

쓰기/스티어링은 전부 기존 operator-console 몫 — 이 앱에는 mutation이 **구조적으로
없다** (tRPC 라우터 전체가 query, 테스트로 강제).

## 실행

```bash
cd viz-shell
npm install
npm run dev          # http://127.0.0.1:3210
```

- 데이터 루트는 기본적으로 `viz-shell/`의 부모 디렉토리. 다른 체크아웃(워크트리 등)에서
  라이브 데이터를 보려면: `AUTOSTOCK_ROOT=/path/to/autostock npm run dev`
- 채팅(뷰 생성)은 로컬 `claude` CLI 구독 인증을 재사용한다 (API 키 불필요 —
  `ANTHROPIC_API_KEY`는 오히려 child env에서 제거됨).

## ⚠️ 보안 — 반드시 지킬 것

- **dev 서버는 `127.0.0.1:3210` 고정** (package.json `dev` 스크립트에 하드코딩).
  `-H 0.0.0.0` 등으로 외부 노출 금지 — 채팅 엔드포인트는 인증이 없고, 로컬 단일
  운영자 전제다 (BR-5).
- 채팅 에이전트의 쓰기는 `src/generated/` 이하만, 읽기는 `viz-shell/` 이하만 허용
  (`src/server/chat/boundary.ts` — 코드로 강제, deny-by-default, 심링크 탈출 차단).
  거부는 채팅에 ⚠️로 표시된다. **경계 규칙을 바꾸면 반드시
  `tests/server/boundary.test.ts`에 케이스를 추가할 것.**
- SDK 자식 프로세스 env에서 트레이딩/스티어링 시크릿 제거
  (`src/server/chat/sanitize-env.ts`).

## 사용법

- **Overview 탭(시드)**: 계좌 카드 / equity curve(7·30·90d) / 포지션 테이블
  (행 클릭 → thesis 마크다운). 5초 폴링 — 로컬 파일 읽기라 데몬 무영향.
- **뷰 생성**: 채팅에 "심볼별 미실현 손익 막대차트 뷰 만들어줘" 식으로 요청.
  생성되면 탭이 자동 추가·활성화된다.
- **뷰 재성형(reform)**: 같은 채팅에서 "그 뷰에 벤치마크도 겹쳐줘"처럼 수정 요청 —
  뷰 1개 = 파일 1개라 부분 수정이 빠르다.
- **탭 닫기(×) = 숨김** (localStorage). 파일은 그대로 — 상단 "숨긴 뷰 (n)▾"에서 복원.
  파일 삭제는 채팅으로 지시 ("hello 뷰 파일 지워줘").
- **New chat**: 세션만 리셋. 뷰 파일/탭은 유지.
- 깨진 생성 뷰는 **해당 탭만** 에러 표시(셸/다른 탭 무사) — 채팅으로 수정 요청하면 된다.

## 구조

```text
viz-shell/
├── src/server/          # C1 paths(경로 화이트리스트) · C3 schemas(zod 미러)
│   │                    # C2 safe-read(원자/tail/stat-stable 3종)
│   ├── routers/         # C4 portfolio tRPC — 전부 query
│   └── chat/            # C5 boundary·sanitize-env·session-store·claude-runner
├── src/app/             # 페이지 + /api/trpc + /api/chat(+reset)
├── src/components/      # C6 셸 UI (탭/오버뷰 위젯/채팅 패널/ErrorBoundary)
├── src/generated/       # 에이전트가 쓰는 유일한 디렉토리 (_example.tsx = 계약 모범)
└── tests/               # vitest + fast-check (경계 거부 테스트 포함)
```

`npm test` (vitest), `npm run typecheck` (tsc).

주의: dev는 **webpack 모드**(`--turbopack` 금지) — 생성 뷰 자동 발견이
`require.context`에 의존한다 (`src/components/view-host.tsx`).
