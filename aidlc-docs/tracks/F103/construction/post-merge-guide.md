# 적용 후 확인

## 적용 범위

공유 executor의 의도 순서 처리와 Toss shadow의 보호·품질·보고가 변경된다. 기존 장부와
종료일, 고정 모델 설정, 처리 완료된 결정은 이어 쓴다. 어제 누락된 SELL을 소급 실행하지 않는다.
Opus 실행 중 코드 교체 지점은 `runtime_revisions`에 F103으로 남는다.

## 두 dry 실험

- `tmux attach -t autostock`: Opus 연구 + Sonnet 감시, 기존 trial-01을 이어서 관찰.
- `tmux attach -t toss-fable`: Fable 연구 + Sonnet 감시의 독립 예약 실행.
  기존 예약인 **2026-11-24 23:25 KST 초기화 / 23:30 정규장 개장 후 첫 턴**을 유지한다.
  초기화 전에는 account.json이 없는 것이 정상이다. 호스트와 tmux가 살아 있어야 한다.

```bash
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-01 report
venv/bin/python -m src.evals.toss_shadow --dir research-comparisons/toss-shadow/trial-fable-20261124 report
```

Fable report 명령은 예약 초기화 이후 사용한다. 두 tmux의 report 창도 결과를 갱신한다.
지금은 장외이므로 market_open=false와 모델 호출 수 유지가 정상이다. 개장 후 확인 항목:

1. health.as_of가 계속 갱신되고 F103 runtime_revisions가 있는지 확인한다.
2. quote_quality의 as_of/status, fresh_value_pct, indicative/unavailable_symbols를 함께 본다.
   degraded는 제한된 소액 stale 평가이며 모든 종목의 체결 허용을 의미하지 않는다.
3. SELL 제출, 부분 체결, 이후 보호 수량을 workspace/execution_outcomes.jsonl과
   account.json의 orders/fills로 대조한다. report/account의 recent_fills에서 체결 원인을 확인한다.
4. 같은 세션 관측 구간끼리 session_performance를 비교한다. first-fill 이후 시작된 구간은
   start_fill_count로 식별한다. 두 실험의 시작 잔고와 모델 노력이 달라 전체 누적 수익의
   차이를 순수한 모델 성능 차이로 해석하지 않는다.

## 검증 상태와 복구

mock 통합/전체 회귀 및 과거 스냅샷 재분류 완료. 2026-11-24 11:49 KST에 장외 재시작 검증 완료:
Opus F103 관찰 주기 2회 이상 진행, health=ok. 기존 장부의 핵심 필드와 커서 hash 동일,
체결 8건/턴 7회 보존. Fable의 launch/예약 파일 hash도 동일하며 새 대기 프로세스가 정상이다.
두 실험의 run/report 창이 모두 살아 있다. 상세 검증은 private restart-before.json과
restart-after.json, 적용 전 백업은 opus-before-F103.tar.gz에 남겼다.
새 정규장에서 실제 stale 재조회 성공률과 모델 판단 결과는 아직 관측하지 않았다.
세금·비용 가정과 실계좌 읽기 전용 경계는 기존대로 유지한다.

문제 시 해당 tmux의 run 창에서 Ctrl-C로 dry runner만 중지한다. 적용 전 private 백업과
검증 기록은 `research-comparisons/F103/`에 둔다. 코드 롤백은 F103 merge commit을 확인한 뒤
`git revert -m 1 dc2b939`를 사용한다. 백업 장부로 복원하면 적용 후 가상 체결이
사라지므로, 현재 장부를 먼저 별도 보관하고 새 구간으로 표시한다.
