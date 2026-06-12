# R8 post-merge guide — agent/ 재구조화 (-m 경로 클린브레이크)

## 무엇이 바뀌나
`src/agent/` 최상위 9모듈이 `logs/`·`learning/` 서브패키지 + `reports.py`로 이동(코드 동작 불변).
**유일한 외부 변화**: 수동 진입점 `python -m src.agent.equity_log` → **`python -m src.agent.logs.equity`**
(shim 없음; non-src 참조 0이라 cron/runbook 영향 없음 — 수동 호출 습관만).

## 체크리스트
1. 데몬: 다음 attach 시 F43 자가치유 1회 재시작(또는 `autostock` 재실행).
2. 스모크: research/eod 턴 1회 후 `workspace/agent_reports/<turn_id>.json` 생성 확인(데이터 경로 불변)
   + `workspace/turns.jsonl`·equity CSV 정상 append.
3. `.gitignore`: `!src/agent/logs/` negation 추가됨 — 런타임 `logs/` ignore가 소스 디렉터리를
   삼키지 않도록(이 negation 없으면 새 파일이 조용히 untracked).

## 롤백
revert -m 1 한 번. 데이터 경로/스키마 불변이라 데이터 마이그레이션 없음.

## 범위 밖 (불변)
`workspace/agent_reports/` 데이터 디렉터리명(TUI가 읽는 외부 표면), 코어 5파일, 헌장 내용.
