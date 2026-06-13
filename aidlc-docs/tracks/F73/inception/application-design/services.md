# F73 — Services (오케스트레이션)

서비스 계층은 2개 플로우로 구성된다. 둘은 서로 독립이며 공유 상태가 없다
(채팅이 죽어도 데이터 뷰는 동작, 역도 성립).

## S1. 데이터 조회 플로우 (요청-응답, 동기)
```text
[브라우저: 뷰 컴포넌트(기본/생성)]
   → tRPC react-query 훅 (폴링 refetchInterval)
   → C4 PortfolioRouter (zod 입력 검증)
   → C2 SafeRead (표면별 전략) ← C1 Paths (화이트리스트 경로)
   → 파일시스템 (read-only)
```
- 단방향. mutation procedure가 **존재하지 않는다** — 라우터 계층에서 읽기 전용이 구조적.
- 폴링 주기는 뷰가 선택(기본 5s) — 데몬 부하 무관(로컬 파일 읽기).

## S2. 뷰 생성 플로우 (스트리밍, 비동기 부수효과 = 파일 생성)
```text
[브라우저: 채팅 패널] --POST /api/chat-->
C5 route.ts
   → SessionStore.resume (명시적 단일 세션)
   → claude-runner.runTurn()
       · sanitizeEnv: 스티어링 토큰 제거 후 SDK 스폰
       · query() 메시지 루프:
           assistant 텍스트  → text-delta 스트림
           tool_use          → checkBoundary(C5b)
                                ├ allow → 실행 + tool-activity 요약 스트림
                                └ deny  → 사유 SDK 반환 + boundary-denied 스트림
   → [SDK가 viz-shell/src/generated/<view>.tsx 작성]
   → Next.js dev 서버 HMR: require.context 무효화 → view-host 재평가
   → [브라우저: 새 뷰 lazy 마운트 (ErrorBoundary 격리)]
```
- **시스템 프롬프트 계약** (claude-runner 상수): 너는 viz-shell 뷰 생성기다 —
  ① 컴포넌트 파일 1개만 `generated/`에 작성(레지스트리 수정 불필요·금지),
  ② 데이터는 반드시 tRPC 훅(예제 `_example.tsx` 참조)으로 접근,
  ③ default export + 명명 규약, ④ 외부 fetch/직접 fs 금지.
- 세션 리셋: 채팅 패널 "New chat" → SessionStore.reset() (tRPC mutation이 아닌
  chat 경로의 보조 엔드포인트 — 데이터 라우터의 read-only 불변 유지).

## S3. (비채택) 데몬 연동 서비스
- 데몬 IPC/프로세스 연동은 없다. viz-shell은 파일시스템 스냅숏만 본다 —
  데몬 다운 시에도 마지막 산출물로 렌더 (fail-honest: snapshot null이면 null 표시).
