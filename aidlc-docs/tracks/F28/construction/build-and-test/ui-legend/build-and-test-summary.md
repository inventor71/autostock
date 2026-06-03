# Build and Test Summary — ui-legend (F28)

> Track: F28 · Worktree: `.claude/worktrees/F28` · 규모에 맞춘 단일 요약(소형 트랙).

## Build Status
- **Build Tool**: bun 1.3.14 (parent `operator-console/`는 빌드 단계 없음 — MCP 서버는 `bun run mcp-server.ts`로 직접 실행).
- **Typecheck**: parent에 tsconfig/typecheck 스크립트 없음 → `bun test`가 TS 파싱·실행을 검증(steer-handler/parser import + `import.meta.url` legend 로드 성공). 서브모듈 cli 코드 미변경(doc 1개)이라 tsgo 영향 없음.
- **Status**: ✅ Success (실행 가능, 0 new deps).
- **Artifacts**: `operator-console/src/ui-legend.json`(21 엔트리) + 수정된 `{parser,steer-handler,mcp-server}.ts` + 서브모듈 `tui-trading/AGENTS.md`.

## Unit Tests
- **Command**: `bun test ./test/` (worktree `operator-console/`).
- **Total**: 131 pass / **0 fail** (8 files). 신규 4 (parser +1, steer-handler +3).
- **신규 커버리지**: `/ui-legend` readOnly verb 파싱 + element를 `args.raw`에 보존 / 전체 legend / 단일 element(meaning 포함) / unknown→not-found 에러.
- **Status**: ✅ Pass.

## Integration / Runtime 검증
- **방식**: 실제 `handleSteerRead`(MCP 도구가 호출하는 그 함수)를 런타임에서 직접 호출.
- **결과**:
  - `/ui-legend` → 21 엔트리 반환.
  - `/ui-legend topbar.today_cost` → 1 엔트리, "$6.01 = 오늘 턴 비용 합계" 설명 (원래 "모름" 문제 해결 확인).
  - `/ui-legend timeline.marker.wake`, `/ui-legend sidebar.account` → 각 1 엔트리.
  - `/ui-legend does.not.exist` → `error: element ... not found`.
- **검증 포인트**: import.meta.url 로드 / element split(handler) / exact-match 필터 / not-found 경로 모두 동작.
- **Status**: ✅ Pass.

## Performance Tests
- **N/A** — 정적 파일 read + 배열 필터(메모리). 부하·확장성 관심사 없음.

## Security Tests
- **N/A** (Q5=B, 확장 비활성). 읽기 전용 verb, 쓰기/주문 경로 무관, 비밀 미노출, 신규 네트워크 의존 0. F26 권한 미변경.

## Additional
- **Contract Tests**: N/A — schema.ts/golden contract 미관여(READ_VERBS pseudo-verb는 SteeringVerb 아님).
- **E2E (수동)**: 선택 — normal 모드 콘솔에서 "탑바 $ 뭐야?" → 에이전트가 description의 `/ui-legend`를 보고 호출 → 설명. (런타임 검증으로 핸들러 경로는 이미 확인.)

## Overall
- **Build**: ✅ Success
- **All Tests**: ✅ Pass (131/0 + 런타임 검증)
- **Ready for merge**: Yes

## Invariants 재확인
파이썬 데몬 변경 0 · schema.ts/golden contract 미관여 · 0 new deps · readOnly verb · F26 권한 미변경.

## 알려진 사항
- 전체 repo `bun test`(서브모듈 포함)는 opencode fork 자체 테스트의 pre-existing timeout 1건 포함(bash-tool 취소, F28 무관). F28 범위 `./test/`는 131/0.

## Next
머지 단계: 서브모듈 `feat/F28`(03bc5b1)를 fork main에 먼저 머지 → 부모 gitlink 갱신 → parent `feat/F28`(9eefceb) → main. (사용자 승인 후.)
