# R10 post-merge guide — intraday 데이터 모듈 `-m` 경로 변경 (클린 브레이크)

## 무엇이 바뀌나
`src/data/intraday_*.py` 4개 모듈이 `src/data/intraday/` 서브패키지로 이동했다.
**운영자용 `-m` CLI 경로가 바뀌었고, 옛 경로 호환 shim은 없다** (2026-06-08 클린 브레이크 결정).

| 옛 경로 (동작 안 함) | 새 경로 |
|---------------------|---------|
| `python -m src.data.intraday_collector backfill --days 30` | `python -m src.data.intraday.collector backfill --days 30` |
| `python -m src.data.intraday_collector today` | `python -m src.data.intraday.collector today` |
| `python -m src.data.intraday_analysis [...]` | `python -m src.data.intraday.analysis [...]` |

## 전제 조건
- 데몬 **코드 동작은 불변**(데몬은 이 모듈을 import하지 않음; F29 codebase tree 표시 라벨만 갱신).
  단, merge로 HEAD SHA가 바뀌므로 **F43 버전-스큐 자가치유가 다음 콘솔 attach 시 데몬을 1회
  자동 재시작한다**(`launcher/daemon.ts` — 의도된 정상 동작, ~수 분 health-wait). 재시작을
  stale-code 회귀로 오인하지 말 것. in-flight 턴이 있으면 attach를 턴 사이로 미루는 게 안전.
- env/config 변경 없음. CSV 데이터 디렉터리(`data/intraday/`, gitignored)는 그대로 — 기존 수집 데이터 재사용됨.

## 실사용 확인 체크리스트
1. `python -m src.data.intraday.collector --help` → usage 출력 (exit 0).
2. `python -m src.data.intraday.analysis --help` → usage 출력 (exit 0).
3. (선택) `python -m src.data.intraday.collector today --symbols AAPL` → `AAPL: N sessions` 로그
   (collector.py:121). **멱등 확인은 로그가 아니라 재실행 후 `data/intraday/AAPL.csv` 행 수 불변**으로
   본다 — upsert 반환/로그의 N은 입력 행 수라 재실행 시에도 같은 값이 찍힌다(중복 적재 아님).
4. 옛 경로를 박아둔 **개인 cron/셸 별칭/노트**가 있으면 위 표대로 갱신 (repo 내 cron/runbook 참조는 0건 확인됨 — Stage 1 전수).

## 롤백
`git revert -m 1 <merge-sha>` 한 번으로 원복 (`/ai-dlc-merge`는 `--no-ff` merge commit이므로
**`-m 1` 필수** — 없으면 git이 거부). 데이터 파일 무관, 순수 코드 이동.

## 알려진 한계 / 범위 밖
- codekb(`aidlc-docs/codekb/nfr-design.md`)의 옛 경로 언급은 CI가 다음 refresh에서 자동 갱신 (single-writer=CI).
- `src/agent/intraday/`(에이전트 의사결정 루프)는 이 트랙과 무관 — 변경 없음.
