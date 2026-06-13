# Integration Test Instructions — F73 viz-shell

단일 유닛이지만 외부 통합 표면이 3개 있다: (1) 데몬 산출물 파일 읽기, (2) Claude
Agent SDK 서브프로세스, (3) HMR 자동 레지스트리. 단위 테스트로 못 잡는 이 경계는
**라이브 스모크**로 검증한다(아래는 수동 절차 — 코드 생성 단계에서 1회 수행 완료).

## 사전
```bash
cd viz-shell && npm install
AUTOSTOCK_ROOT=/abs/path/to/autostock npm run dev   # 실데이터 루트
# 데몬이 산출물을 쓰고 있어야 함(steering/snapshot.json, workspace/equity.jsonl, positions/*.md)
```

## IT-1 — 데이터 라우터 ↔ 실파일
```bash
curl -s http://127.0.0.1:3210/api/trpc/portfolio.snapshot          # account/positions 실수치
curl -s http://127.0.0.1:3210/api/trpc/portfolio.listPositions     # 심볼 배열
curl -s "http://127.0.0.1:3210/api/trpc/portfolio.equity?input=%7B%22sinceDays%22%3A7%7D"
curl -s "http://127.0.0.1:3210/api/trpc/portfolio.thesis?input=%7B%22symbol%22%3A%22RTX%22%7D"
curl -s "http://127.0.0.1:3210/api/trpc/portfolio.thesis?input=%7B%22symbol%22%3A%22..%2Fetc%22%7D"  # 400 (zod 거부)
```
**기대**: 앞 4개 실데이터 200, 마지막 경로형 symbol은 400. 데몬 중단 시 snapshot
null + 위젯별 placeholder("snapshot 없음 — 데몬 미가동?"), 전체 빈 화면 금지.

## IT-2 — 채팅 SDK 라이프사이클 (실 서브프로세스)
```bash
curl -s -N -X POST http://127.0.0.1:3210/api/chat -H "Content-Type: application/json" \
  -d '{"messages":[{"id":"1","role":"user","parts":[{"type":"text","text":"Create src/generated/smoke.tsx rendering Hello."}]}]}'
```
**기대**: SSE 스트림에 `text-start/delta/end` + `data-tool-activity`(Read _example,
Write smoke.tsx), `[DONE]`. 서버 로그에 `turn start`/`turn end`(세션 id). 파일
`src/generated/smoke.tsx` 생성. 2턴째 동일 세션 id로 resume.

## IT-3 — 경계 (보안 통합)
```bash
# workspace 직접 읽기 요청 — 코드 경계가 거부해야 함
curl -s -N -X POST http://127.0.0.1:3210/api/chat -H "Content-Type: application/json" \
  -d '{"messages":[{"id":"1","role":"user","parts":[{"type":"text","text":"Read /abs/autostock/workspace/equity.jsonl with the Read tool and quote it."}]}]}'
```
**기대**: `data-boundary-denied`(또는 에이전트가 계약 인지 후 자가 거부 + tRPC 경유
제안). workspace 파일 본문이 응답에 노출되지 않음.

## IT-4 — 단일 in-flight + reset 레이스
```bash
# 턴 진행 중 두 번째 POST → 409
# 턴 진행 중 reset → 409 (세션 부활 레이스 차단; code-review 수정)
curl -s -X POST http://127.0.0.1:3210/api/chat/reset -w " [%{http_code}]"   # 유휴 시 200
```

## IT-5 — HMR 자동 레지스트리
- `src/generated/probe.tsx`(default export + meta.title) 생성 → 수 초 내 새 탭 노출.
- 삭제 → 탭 제거. 깨진 뷰(throw) → 해당 탭만 ErrorBoundary fallback, 셸/다른 탭 무사.

## 검증 상태 (2026-06-13, Code Gen 단계서 수행)
IT-1·2·3·5 라이브 통과. IT-4 reset 409/200 통과. 스모크 산출물 정리 완료.
