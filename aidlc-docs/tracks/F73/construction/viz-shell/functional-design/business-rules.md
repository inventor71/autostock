# F73 viz-shell — Business Rules

## 경계·보안 (BR-1 ~ BR-5)
- **BR-1 (쓰기 경계)**: SDK Write/Edit류는 `viz-shell/src/generated/` 이하만 허용.
  그 외 전 경로 deny + 사유 반환 + UI ⚠️. 심볼릭 링크 탈출은 realpath 정규화로 차단.
- **BR-2 (읽기 경계)**: SDK Read/Glob/Grep은 `viz-shell/` 이하만. `workspace/`·
  `steering/` 직접 읽기 금지 — 데이터 파일 본문(예: thesis)을 SDK 컨텍스트에 넣지
  않는다 (prompt injection 벡터 차단). 뷰가 데이터를 쓰려면 런타임 tRPC 훅으로.
- **BR-3 (도구 경계)**: Bash/WebFetch/Task 등 비편집 도구 전부 deny-by-default.
- **BR-4 (env 위생)**: SDK 자식 프로세스 env에서 스티어링 토큰 키
  (`AUTOSTOCK_STEER_TOKEN` 등 — Code Gen에서 실키명 확정) 제거. 단위 테스트 필수.
- **BR-5 (네트워크)**: dev 서버는 `127.0.0.1:3210` 바인딩 고정 (package.json script에
  하드코딩 — 실수로 `--hostname 0.0.0.0` 못 바꾸도록 README 경고 동반).

## 데이터 라우터 (BR-6 ~ BR-9)
- **BR-6 (mutation 0)**: tRPC 라우터에 mutation procedure 금지. 세션 리셋은 chat
  경로(`/api/chat/reset`)의 부속 — 데이터 라우터와 분리 유지.
- **BR-7 (입력 검증)**: 모든 procedure 입력 zod. `symbol`은
  `^[A-Z][A-Z0-9.\-]{0,9}$` + `listPositions()` 결과 대조(이중 화이트리스트).
  경로 문자열을 입력으로 받는 procedure 금지 (C1 상수만 사용).
- **BR-8 (fail-honest)**: 파일 부재/파싱 실패 = null/빈배열 + 서버 warn 로그.
  가짜 기본값 생성 금지. stale 읽기(positions)는 `stale: true` 플래그로 정직 표시.
- **BR-9 (스키마 관용)**: zod 미러는 `.passthrough()` — Python 측 필드 추가가
  viz-shell을 깨지 않게. 필수 필드 결손만 실패로 처리.

## 생성 뷰 규약 (BR-10 ~ BR-13)
- **BR-10 (단일 파일)**: 뷰 1개 = `generated/<kebab-case>.tsx` 1파일. 레지스트리/
  index 수정 금지(자동 발견). `_` 접두 파일은 탭 비노출(예제/유틸용).
- **BR-11 (뷰 계약)**: `export default` React 컴포넌트 +
  `export const meta = { title: string }` (탭 라벨; 부재 시 파일명 변환).
  데이터 접근은 tRPC 훅만, 외부 fetch/직접 fs/dynamic import 금지.
- **BR-12 (시스템 프롬프트 계약)**: claude-runner의 appendSystemPrompt에 BR-10/11을
  영문으로 고지 + `_example.tsx` 참조 지시 + "차트는 recharts 사용" + "파일 쓰기는
  generated/만 허용되며 그 외는 거부된다" 사전 고지 (거부 루프 절약).
- **BR-13 (뷰 표시 상태 분리)**: 탭 닫기 = localStorage 숨김 목록 추가(파일 무접촉).
  복원 메뉴 제공. 파일 정리는 채팅 지시로만 — UI에 파일 삭제 버튼 금지 (UAQ 결정).

## 채팅·세션 (BR-14 ~ BR-16)
- **BR-14 (단일 세션)**: 세션 id 1개 파일 영속(`viz-shell/.cache/session.json`,
  gitignore). 매 턴 resume. "New chat" = reset 후 신규 발급.
- **BR-15 (동시 턴 금지)**: in-flight 턴 존재 시 신규 POST는 409 + UI 안내
  (단일 운영자 전제 — 큐 구현 안 함).
- **BR-16 (스트림 이벤트)**: `text-delta`(assistant 텍스트), `tool-activity`
  (도구명+대상 상대경로 요약 1줄), `boundary-denied`(⚠️ 도구+경로+사유).
  raw tool 로그 전체는 노출하지 않음 (UAQ 결정 — 요약 수준).

## 로깅 (BR-17)
- **BR-17**: 서버 콘솔에 구조화 로그 — 채팅 턴 시작/종료(세션 id, 소요), 경계 거부
  (도구/경로), 라우터 파싱 실패 카운트. **민감값(계좌 수치, thesis 본문) 비기록**
  (SECURITY-03 충족 수준의 운영 로그).
