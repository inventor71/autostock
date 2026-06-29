# F94 — Build & Test Summary

## 변경 요약
- `operator-console/src/account-truth.ts` (신규): provider-aware 계좌-read. account_farm →
  데몬 snapshot.json, 그 외 → AlpacaDataClient 위임.
- `operator-console/src/mcp-server.ts`: 계좌-truth 5개 read 툴을 `account.*` 경유로 라우팅
  (+설명 갱신). 시장데이터/mutating 불변.
- `operator-console/src/alpaca-data.ts`: `formatResponse` export(스냅샷 경로 재사용).
- `operator-console/test/account-truth.test.ts` (신규): provider 라우팅 + degrade 테스트.

## 테스트 결과
- `bun test ./test` (operator-console): **187 pass / 0 fail** (신규 5 포함).
- 실데이터: 라이브 aggressive snapshot.json → reader → **HD 4 / equity 79,651** (RTX/TMO 없음).

## 비고 (사전-존재, F94 무관)
- 전체 `bun test`(루트)는 `cli/`(opencode 포크) 하위 테스트까지 수집 → 이 worktree에 cli 의존성
  미설치로 다수 실패(solid-js 등 missing). main(F94 전)에서도 동일. 그래서 변경 패키지인
  `operator-console/test`로 한정 실행.
- operator-console/src엔 tsconfig 없음 — bun이 TS 직접 실행(별도 typecheck 단계 없음). bun test가
  파싱/로드 검증 겸함.

## 머지 후
- post-merge-guide.md: 콘솔 재접속(quit→attach)으로 새 mcp-server 코드 로드(데몬 재시작 불필요),
  채팅 "보유" → HD/HON/GILD 확인.
