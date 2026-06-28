# F92 Post-Merge Guide — 브로커 provider 정합성 + 멀티 인스턴스 격리 복구

> **대상**: 운영 중인 Docker prod 3개 인스턴스(aggressive/balanced/conservative).
> 코드 정합은 **머지로 자동 반영**(컨테이너가 `.:/app`로 main 체크아웃을 마운트)되지만,
> ① 이미 떠 있는 데몬은 **구버전 코드를 메모리에 들고** 있고, ② 워크스페이스는 **유령 계좌
> 기준 오염 상태**다. 아래 절차로 데몬 재시작 + 워크스페이스 reconcile을 해야 실효된다.

## prod 브랜치에서 무엇이 바뀌나
- agent가 손익/포지션/주문을 읽는 모든 경로(`python -m src.agent.tools account`,
  `python -m src.agent.logs.equity`, `scripts/status.py`)가 **provider-aware factory**를 거친다.
- → account_farm 인스턴스는 이제 **자기 sub-account**를 읽는다(기존: 공유 Alpaca 계좌 오독).
- 시장데이터(alpaca 키)는 그대로 공유 — 정상.

## 사전 조건
- [ ] F92가 `main`에 머지됨.
- [ ] 작업은 메인 체크아웃(`/home/jihoonpark/Project/autostock`)에서 실행
      (컨테이너가 마운트하는 그 트리).
- [ ] 미국장 종료/한가한 시간대 권장(데몬 재시작 중 턴 누락 최소화). 6/28은 토요일(휴장).

## 절차 (인스턴스마다 1회)

각 인스턴스(`aggressive`/`balanced`/`conservative`)에 대해:

```bash
cd ~/Project/autostock
# (선택) 현재 유령 보유 확인 — 수정 전이면 RTX/TMO/equity 99,939가 보일 수 있음
scripts/prod-run.sh reconcile aggressive
```

`reconcile`이 하는 일:
1. 데몬 정지(볼륨 보존).
2. 워크스페이스의 **계좌종속 파일을 `_pre_f92_archive_<ts>/`로 이동**(삭제 아님):
   `decisions.jsonl, trades.jsonl, equity.jsonl, execution_outcomes.jsonl,
   execution_log.jsonl, turns.jsonl, pending_approvals.json, .fills.cursor,
   .executor_state.json, positions/, agent_reports/, daily/`.
3. **보존(계좌무관 시장 아티팩트)**: `CLAUDE.md, lessons.md, regime.md, watchlist.md,
   screening/, sentiment/, surge/, holdings/, .sessions/, .news_seen.json`.
4. 데몬 재시작 → 다음 턴부터 **자기 sub-account 실보유**로 positions/equity 재구축.

> 데몬을 직접 재시작만 하고 워크스페이스는 그대로 두고 싶다면 `down`+`up`만 해도 코드는
> 실효되지만, 유령 RTX/TMO thesis/journal이 남아 혼선을 준다. reconcile 권장.

## 실사용 검증 체크리스트 (real-data)

각 인스턴스에서:

- [ ] `scripts/prod-run.sh attach <name>` → 콘솔에서 "현재 보유/손익 알려줘".
      기대값(라이브 확인된 실 sub-account):
      - aggressive → **HD ~4주**, equity ~**79,651**
      - balanced → **HON ~9주**, equity ~**75,928**
      - conservative → **GILD ~14주**, equity ~**51,254**
- [ ] **RTX / TMO 가 더 이상 안 보임** (유령 데이터 소멸).
- [ ] 세 인스턴스의 보유/equity가 **서로 다름** (수정 전엔 셋 다 동일 99,939였음).
- [ ] CLI 직접 확인: 컨테이너 안에서
      `python -m src.agent.tools account` 로그 첫 줄이 **`AccountFarmBroker initialized`**
      (기존: `AlpacaBroker initialized`).
- [ ] `scripts/prod-run.sh logs <name>` 에 broker/account 관련 에러 없음.

## 롤백
- 코드: `main`에서 F92 머지 revert → 컨테이너 데몬 재시작.
- 데이터: reconcile은 **이동만** 하므로 `workspace/_pre_f92_archive_<ts>/`에서 파일을 되돌리면
  원복(단, 되돌리면 다시 유령계좌 기준 기록으로 회귀).

## 알려진 한계 / 범위 외
- `scripts/status.py` fills 테이블은 Alpaca SDK 전용 — account_farm에선 "n/a" 행으로 degrade
  (positions/orders/equity는 정상). monitor.sh 운영자 대시보드 한정.
- benchmark/backtest 경로(`src/benchmark/runner.py`)는 이번 트랙 범위 외(폐기 예정,
  [[backtest-deprecation-pending]]).
- verify 이미지 `pyarrow` 부재로 인한 intraday parquet 테스트 실패는 별도 이슈(F92 무관).
