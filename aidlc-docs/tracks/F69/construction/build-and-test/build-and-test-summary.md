# F69 Build & Test Summary — Health Check TUI 통합

## 변경 요약
- **Python producer**: 데몬이 5분마다(설정) cheap subset health를 `steering/health.json`에 발행.
- **TS consumer**: TUI 상단바 health 글리프 + 클릭 시 9차원(실제로는 cheap 5차원) 상세 오버레이.

## 빌드
- Python: 빌드 단계 없음(인터프리터). import 정합성은 테스트/스모크로 확인.
- TS(operator-console/cli): `bun install --frozen-lockfile`(worktree-setup이 수행) → tsgo 타입체크.

## 테스트 실행 & 결과
| 항목 | 명령 | 결과 |
|------|------|------|
| F69 단위테스트 | `venv/bin/python -m pytest tests/test_f69_health_publish.py -q` | **6 passed** |
| 회귀(steering+agent) | `pytest tests/test_steering_*.py tests/test_agent.py tests/test_f69_health_publish.py -q` | **187 passed** |
| TS 타입체크(monorepo) | `cd operator-console/cli && bun run typecheck` | **19/19 successful** |
| 라이브 스모크 | 실 settings로 cheap dispatcher 발행 → health.json 계약 검증 | **OK** (interval=300, cheap 차원만, broker init 로그 0) |

### 핵심 회귀 가드 (critic HIGH)
`test_periodic_publish_excludes_expensive_dimensions` — 주기 발행 페이로드에 broker/llm/risk/
data_pipeline 차원이 **절대 포함되지 않음**을 고정. (전체 9차원은 scripts/health.py 한정.)

## 통합 관점
- Producer↔Consumer 계약: `health.json`의 `overall`(enum) / `dimensions`(dict) /
  `publish_interval_seconds`(int) — TS `HealthReport` 타입 + `use-health-data` 훅과 일치(스모크로 검증).
- 기존 `scripts/health.py` 전체 9차원 경로 무변경(공존).

## 알려진 한계
- 주기 발행은 cheap subset(broker/llm live 미포함) — 깊은 점검은 `scripts/health.py` 수동.
- TUI 오버레이 렌더는 타입체크 + 컴포넌트 패턴(turn-overlay) 일관성으로 검증; 실제 터미널
  렌더 확인은 post-merge-guide의 실사용 체크리스트로 수행.
