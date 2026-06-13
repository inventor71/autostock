# Build & Test Summary — F73 viz-shell

## 상태: ✅ GREEN (장기 브랜치 — merge-awaiting 전환 안 함)

| 게이트 | 결과 |
|---|---|
| `npm run typecheck` (tsc --noEmit) | ✅ 클린 |
| `npm test` (vitest) | ✅ **10 files / 108 tests pass** |
| `npm run build` (next build) | ✅ Compiled successfully (라우트 5, `/`=Static, api 3=Dynamic) |
| 경계 거부 테스트 (보안 성공 기준 ③, blocking) | ✅ 전건 green (Glob `..` 케이스 포함) |
| 라이브 통합 스모크 (IT-1~5) | ✅ 실데이터 렌더·SDK 턴·경계·HMR·reset 409 |
| Security Baseline 컴플라이언스 | ✅ 비준수 0 (준수 7 / N/A 8) |

## 테스트 전략 요약
- **단위**: 서버 7파일(경계·안전읽기·스키마·라우터·env·세션·reset) + UI 3파일.
  PBT(fast-check)로 안전읽기 임의 절단·스키마 직렬화 라운드트립.
- **통합**: 라이브 스모크 — 외부 통합 3표면(파일/SDK/HMR)은 fake로 증명 불가하므로
  실서버+실데이터로 수동 검증(integration-test-instructions.md).
- **성능**: N/A(로컬 단일 사용자) + NFR-6 폴링 무영향 관찰.

## 코드리뷰 라운드 (반영 완료)
/code-review high — 8건 수정(보안 1: Glob `..` 경계 우회 차단 포함). 상세는
`construction/viz-shell/code/code-summary.md` 말미.

## 머지 정책 (중요)
**장기 브랜치 `vibeshell`.** Build & Test가 green이어도 **`merge-awaiting`으로
전환하지 않는다** — 사용자가 명시적으로 "안정됐다, 머지하자"고 선언할 때까지 `active`
유지(state.md Merge Policy, 루트 Registry `do-not-enqueue`). `/ai-dlc-merge` 큐 조기
진입 금지. main의 유의미한 머지마다 vibeshell을 rebase해 디버전스 상한.

## 남은 한계 / 범위 외
- Turbopack 비호환(require.context) — webpack dev 고정(문서화).
- 채팅은 단일 운영자 전제(인증 없음) → 127.0.0.1 바인딩이 유일 방어. 외부 노출 금지.
- 생성 뷰 품질은 에이전트 출력에 의존 — ErrorBoundary로 격리하되 자동 수복은 채팅 지시.
