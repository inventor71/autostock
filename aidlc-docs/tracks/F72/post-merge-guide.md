# F72 — Post-Merge Guide (스크리닝 결과 로깅 + /screening)

## 무엇이 바뀌나 (prod 브랜치)

1. **scoreboard 실행 시 자동 저장**: `python -m src.agent.tools scoreboard`가 **전체
   유니버스로** 돌 때마다 (research turn 포함) `workspace/screening/<ET날짜>.scan.json`에
   quant 스냅샷이 저장된다 (같은 날 재실행 = 덮어쓰기, 최신 실행 기준).
   `--symbols` 부분 실행은 **저장하지 않는다** — 부분 스캔이 그날의 전체 레코드를
   덮어쓰지 않게 하기 위함 (critic 반영).
2. **research 프롬프트에 verdict 의무**: 다음 research turn부터 에이전트가 실제 검토한
   후보별로 `workspace/screening/<ET날짜>.verdicts.jsonl`에
   `{ts, symbol, verdict(entered|watchlist|passed), reason}` 한 줄씩 남긴다.
3. **TUI 새 read verb**: `/screening` (최신), `/screening 2026-06-10` (날짜 지정) —
   verdict 목록 + quant 스캔 표를 함께 반환. steer_read 도구 설명에도 안내 추가됨.

## 사전 조건

- **데몬 재시작** 필요 (프롬프트 변경 반영 — 에이전트 세션은 데몬이 스폰).
- **operator console(MCP 서버) 재시작** 필요 (`/screening` verb + 도구 설명).
- 신규 env/config 키 없음. `workspace/screening/`은 자동 생성.

## 실사용 검증 체크리스트

1. 머지 + 데몬/콘솔 재시작 후, 다음 research turn(또는 TUI에서 `/research` 트리거)을 기다린다.
2. `ls workspace/screening/` → 오늘 ET 날짜의 `*.scan.json` 존재, `count`가 유니버스
   크기(~131)와 일치하는지. (턴 전에라도 수동 `python -m src.agent.tools scoreboard`로 — 단 `--symbols` 없이 — 확인 가능)
3. 같은 날짜의 `*.verdicts.jsonl` 존재 + 후보별 한 줄 (LLM 준수 — **첫 턴은 직접 확인 권장**;
   비어 있으면 에이전트가 의무 문구를 무시한 것이므로 프롬프트 강화 필요 신호).
4. TUI에서 `/screening` → "verdicts (n): ..." + "scan (...): 131행" 출력.
   `/screening <어제>` → 어제 데이터 또는 "(no screening data for ...)".
5. "정상" 기준: scan은 매 research turn마다 갱신, verdicts는 통상 5~20줄/턴,
   `entered` 종목은 decisions.jsonl과 부합.

## 튜닝 노브 / 롤백

- verdict 어휘·의무 강도: `src/agent/prompts.py` `_screening_journal_block()`.
- 표시 형식: `operator-console/src/steer-handler.ts` `formatScreening()`.
- 롤백: 커밋 revert로 충분 (데이터 파일은 gitignored workspace 하위라 영향 없음;
  남은 screening/ 파일은 무해, 원하면 삭제).

## 알려진 한계 / 범위 외

- verdicts는 **LLM이 실제 검토한 후보만** — 나머지 ~110개 종목의 "사유"는 없음(quant
  스냅샷으로만 커버). 전수 사유 강제는 비현실적이라 의도된 설계.
- intraday/wake/eod 턴은 verdict 의무 없음 (scoreboard를 돌리면 scan 저장은 됨).
- 과거(이번 머지 이전) 턴의 스크리닝은 소급 불가 — 머지 후부터 쌓임.
- LLM 준수 의존: verdict 기록은 프롬프트 의무이지 코드 강제가 아님 (scan 저장은 코드 강제).
