# F92 Code Generation Plan — Unit-1 (broker factory 통일 + 격리 + surgery)

> 동작 보존 정합성 수정. account_farm 격리는 정상 — agent의 truth 읽기 경로만 provider-aware로.

## A. 코드 (native refactor)
- [x] A1. `src/execution/brokers/factory.py` 신설 — `create_broker(settings)`를 `main.py`에서
      이동(로직 동일: kis|account_farm|alpaca 분기 + unknown provider fail-loud).
- [x] A2. `main.py` — 자체 정의 제거하고 `from src.execution.brokers.factory import create_broker`
      (main.py:285/378 내부 사용 + `main.create_broker` 이름 유지).
- [x] A3. health dims upward import 정리 — `src/monitoring/health/dimensions/{account,broker,risk}.py`
      의 `from main import create_broker` → `from src.execution.brokers.factory import create_broker`.
- [x] A4. **[critical]** `src/agent/tools/__main__.py::_broker()` — 하드코딩 AlpacaBroker 제거,
      `create_broker(get_settings())` 사용.
- [x] A5. **[critical]** `src/agent/logs/equity.py::main()` — 동일하게 `create_broker` 경유.
- [x] A6. `scripts/status.py` — 포지션/주문/equity는 `create_broker` 경유(올바른 계좌).
      시장데이터 client는 alpaca 키 유지(market data는 공유 정상). 비-alpaca에서 fills 테이블이
      Alpaca 내부 API 의존이면 graceful degrade(빈 테이블/경고) — 운영자 대시보드, 결정경로 밖.

## B. 테스트 (회귀 방지)
- [x] B1. `tests/test_broker_factory.py` — provider→클래스 매핑(alpaca→AlpacaBroker,
      account_farm→AccountFarmBroker, kis paper→KisPaperBroker), unknown provider→ValueError,
      live=False kis→NotImplementedError. (기존 `tests/kis/test_integration.py` 패턴 재사용)
- [x] B2. `tests/test_agent_cli_broker.py` — account_farm 설정에서 `src.agent.tools.__main__._broker()`
      및 `src.agent.logs.equity.main()`이 AccountFarmBroker를 만든다(또는 create_broker를 호출한다)
      를 검증(외부 API는 monkeypatch/스텁). **유령-Alpaca 재발 가드.**
- [x] B3. 영향 import 깨짐 없는지(`from main import create_broker` 잔재 0) 점검.

## C. Verify (컨테이너 하네스 — zero prod impact)
- [x] C1. `scripts/worktree-setup.sh --docker-verify` 환경에서 `verify {typecheck,unit}` green.
- [x] C2. (read-only) 실행 중 컨테이너에서 worktree 코드로 `account` 재확인 불가(컨테이너는
      main 마운트). 대신 단위테스트로 provider 분기 보장 + 머지 후 라이브 스모크(아래 D).

## D. 운영 Surgery (리셋+reconcile) — **머지 후 실행** (post-merge-guide.md)
> 실행 컨테이너는 `.:/app`(main 체크아웃)을 마운트 → 코드 수정은 **F92 머지 후** 반영.
> 데몬은 구버전 코드를 메모리에 들고 있으므로 **재시작 필요**(F43 self-heal/런처).
- [ ] D1. F92 머지(main) → /app 코드 정합화.
- [ ] D2. 각 인스턴스(aggressive/balanced/conservative):
      - daemon 정지(`prod-run.sh down <name>` — **--wipe 금지**, 볼륨 보존).
      - workspace **계좌종속 저널 아카이브+리셋**: `decisions.jsonl, trades.jsonl, equity.jsonl,
        execution_outcomes.jsonl, execution_log.jsonl, turns.jsonl, positions/*.md,
        .fills.cursor, .executor_state.json, agent_reports/*` → `workspace/_pre_f92_archive/`로 이동.
      - **보존(계좌무관 시장아티팩트)**: `CLAUDE.md, lessons.md, regime.md, watchlist.md,
        screening/, sentiment/, surge/, holdings/, .sessions/, .news_seen.json`.
      - daemon 재시작(`prod-run.sh up <name>`). 다음 턴에 `account`(수정됨)로 실 sub-account
        truth를 읽어 positions/equity 재구축.
- [ ] D3. 라이브 검증: 각 콘솔/CLI `account`가 자기 sub-account만 보고
      (aggressive=HD4/eq79.6k, balanced=HON9/eq75.9k, conservative=GILD14/eq51.3k), RTX/TMO 소멸.
- [x] D4. 헬퍼 구현 완료: `scripts/prod-run.sh reconcile <name>` (데몬 정지→계좌종속 파일 아카이브
      이동→재시작; --wipe 아님). post-merge-guide.md에 절차/검증 문서화.

## 산출물
- 신규: `src/execution/brokers/factory.py`, `tests/test_broker_factory.py`, `tests/test_agent_cli_broker.py`
- 수정: `main.py`, health dims x3, `src/agent/tools/__main__.py`, `src/agent/logs/equity.py`, `scripts/status.py`, (선택)`scripts/prod-run.sh`
- 문서: `post-merge-guide.md`(surgery 절차 + 라이브 검증 체크리스트)
