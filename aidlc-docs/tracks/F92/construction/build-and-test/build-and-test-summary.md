# F92 — Build & Test Summary

## 변경 요약
- 신규 `src/execution/brokers/factory.py` — `create_broker(settings)` (provider-aware 단일 합류점).
- `main.py` — 자체 `create_broker` 제거, factory에서 import (`main.create_broker` 이름 유지).
- health dims(`account.py`/`broker.py`/`risk.py`) — `from main import create_broker` →
  `from src.execution.brokers.factory import create_broker` (src→main upward 의존 제거).
- **[버그픽스]** `src/agent/tools/__main__.py::_broker()` + `src/agent/logs/equity.py::main()` —
  하드코딩 AlpacaBroker 제거, factory 경유 (account_farm 인스턴스가 자기 sub-account를 읽음).
- `scripts/status.py` — 계좌 truth는 factory 경유; 시장데이터 client만 alpaca 유지; 비-alpaca는
  fills 테이블 graceful degrade.
- `scripts/prod-run.sh` — `reconcile <name>` 서브커맨드 추가(머지 후 surgery용, 아카이브 방식).
- 신규 테스트 `tests/test_broker_factory.py`(7), `tests/test_agent_cli_broker.py`(2).

## 테스트 결과
- **신규 F92 테스트**: 9 passed (factory provider 라우팅 + 에이전트 CLI/equity factory 경유 가드).
- **기존 broker 스위트** (alpaca/account_farm/kis 통합): 84 passed.
- 호스트 venv 전체 관련 영역 green. verify 이미지에서 F92+broker 92 passed.
- `bash -n` : `prod-run.sh` syntax OK.

### 컨테이너 verify(`verify-run.sh run --rm verify unit`)의 사전-존재 실패 17건 — **F92 무관**
- 16건 = `tests/intraday/test_pattern_detection.py`·`test_auto_collect.py` (Parquet store):
  **verify 이미지에 `pyarrow` 미설치** (`importlib.util.find_spec('pyarrow') → None`).
  호스트 venv에서는 동일 테스트 통과. F80 storage 의존성 이슈([[f80-storage-format-rationale]]).
- 1건 = `tests/test_health_publish.py::test_publish_resolves_repo_root_not_above_it`:
  **수정 안 한 main 체크아웃**을 verify 이미지로 돌려도 동일 실패(컨테이너 repo-root 해석 아티팩트).
- 두 부류 모두 F92 변경 전후 동일 → 분리된 무관 실패(F88/F91 선례와 동급). 별도 추적 권장
  (verify 이미지에 pyarrow 추가 / health-publish 컨테이너 경로 해석).

## typecheck 비고
- `verify typecheck`는 operator-console(bun/TS) 대상. F92는 Python-only 변경이라 무관하며,
  worktree에서 bun lockfile frozen drift로 별도 실패(코드 무관).

## 머지 후 필수 작업
- `post-merge-guide.md` 참조 — 코드 정합은 머지로 반영되고, **운영 surgery + 데몬 재시작**은
  머지 후 수동 실행(파괴적·라이브). 그 전까지 3개 인스턴스는 여전히 유령 계좌를 읽음.
