# F97 Build & Test — Summary

## 변경 요약
에이전트 vs S&P500(SPY buy-and-hold) 일별 성과 헤드라인. 기존 `equity.jsonl`(일별 equity+SPY)을
read-time에 조인·정규화 → 누적수익/alpha/오늘델타 → 6개 surface에 노출.

## 손댄 파일
| # | 파일 | 변경 |
|---|---|---|
| 1 | `src/agent/logs/performance.py` | **신규** 순수 코어 `compute_performance` + `load_performance` + CLI `main` |
| 2 | `src/agent/steering/runtime.py` | `_perf_block()` + snapshot dict에 `perf_vs_benchmark`(additive) |
| 3 | `scripts/status.py` | `_summary` 패널에 "vs S&P500" 라인(`_bench_line`) |
| 4 | `operator-console/.../server/autostock/dashboard-read.ts` | `DashboardPayload.perf` + `toPerf` 매핑 |
| 5 | `operator-console/.../app/.../dashboard-source.ts` | 계약 mirror + `toPerf`(camelCase) 매퍼 |
| 6 | `operator-console/.../app/.../dashboard-view.tsx` | Hero 카드에 "vs S&P500" 라인 + `perf?` prop |
| 7 | `operator-console/.../app/.../mobile-shell.tsx` | payload→`perf` 배선 |
| 8 | `operator-console/.../opencode/.../sidebar/autostock.tsx` | 터미널 TUI 사이드바 "vs SPY" 라인 |
| 테스트 | `tests/test_performance.py` (신규, PBT+example), `dashboard-source.test.ts`, `autostock-dashboard.test.ts` | perf 커버리지 |

**미변경**: `agent.py:_eod`(read-time 파생이라 훅 불필요), `equity.py`(read_equity만 재사용), `src/benchmark/`.

## 빌드
- Python: 별도 빌드 없음(인터프리터). `pip install -e .[dev]` 환경.
- TS 콘솔: `cd operator-console/cli && bun install && bun run typecheck` (tsgo).

## 테스트 결과 (2026-07-10, 워크트리)
- **Python 전체**: 1503 passed, 1 failed. 유일 실패 = `tests/test_health_publish.py::test_publish_resolves_repo_root_not_above_it` — **워크트리 경로에서 repo-root 재resolve 아티팩트**(main 체크아웃에서는 통과, F97은 health/dispatch 파일 미변경). F97 무관.
- **Python perf 유닛/PBT**: `tests/test_performance.py` 13 passed (example 7 + PBT 6: scale/zero-alpha/oracle/consistency/robustness/boundary).
- **TS typecheck**: 19/19 successful.
- **TS 유닛**: `dashboard-source.test.ts` 12 pass, `autostock-dashboard.test.ts` 16 pass.
- **Live smoke (실 equity.jsonl)**: `Agent +0.09% | SPY +0.61% | Alpha -0.52% (today -0.42%p, since 2026-05-28, 29d)`. 손계산 일치.

## PBT Compliance (Property-Based Testing = Enabled/Full)
| Rule | 상태 | 근거 |
|---|---|---|
| PBT-01 property 식별 | ✅ | functional-design "Testable Properties" 6개 |
| PBT-02 round-trip | N/A | 손실없는 역함수 쌍 없음(수익률은 단방향 파생) |
| PBT-03 invariant | ✅ | scale 불변, zero-alpha, consistency, boundary |
| PBT-04 idempotency | N/A | 멱등 대상 연산 없음 |
| PBT-05 oracle | ✅ | 손계산 시계열 대조 |
| PBT-06 stateful | N/A | 상태 없는 순수 함수 |
| PBT-07 generator | ✅ | 도메인 생성기(양의 float equity/SPY 시계열, SPY-결측 주입) |
| PBT-08 shrink/seed | ✅ | hypothesis 기본(오버라이드 없음), CI 포함 |
| PBT-09 framework | ✅ | hypothesis (기존 dep) |
| PBT-10 complementary | ✅ | example 7 + PBT 6 병행; 노출 계층은 example(TS)로 커버 |
- 노출 계층(`_perf_block`, TS 매핑) = thin passthrough → PBT N/A, example 테스트로 커버.

## 결론
F97 관련 전 항목 그린. 유일 실패는 F97 무관 워크트리-환경 아티팩트. **merge-awaiting**.
