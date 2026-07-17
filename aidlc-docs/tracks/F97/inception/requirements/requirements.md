# F97 요구사항 — Daily 성과 평가: 에이전트 vs S&P500

## Intent Analysis (의도 분석)

- **User Request (원문)**: "autostock을 평가를 하고 싶어. 얘를 들어서 s&p500 에 그냥 넣었을때에 비해서 얼마나 잘하고 잇는지 daily 로 확인할 수 있도로 한다거나"
- **Request Type**: New Feature (기존 데이터 위에 새 지표/노출 추가)
- **Scope Estimate**: Multiple Components — Python 지표 계산 + EOD 훅 배선 + 스냅샷 payload + TUI 렌더 + 모바일 대시보드 payload
- **Complexity Estimate**: Simple~Moderate — 데이터·지표 라이브러리가 이미 존재. 신규 로직은 "SPY buy-and-hold 정규화 + 누적수익/alpha 계산"이라는 순수 함수 하나가 핵심. 나머지는 배선·표시.
- **Depth**: Standard

## Background (현 상태 — Workspace Detection 결과)

이미 존재하는 것:
- `workspace/equity.jsonl` — EOD마다 `{ts, date, equity, cash, ..., benchmark:{SPY, QQQ, ^VIX}}` 한 줄씩 영속화.
  - Writer: `src/agent/logs/equity.py:record_equity` (`snapshot()` + `fetch_benchmark()`), `src/trading/modes/agent.py:_eod`(≈15:55 ET)에서 호출.
  - Reader: `src/agent/logs/equity.py:read_equity()`.
- 지표 라이브러리: `src/backtest/metrics.py`(pandas: sharpe/mdd/total_return), `src/benchmark/metrics.py`(pure-python: cum_return/vol/mdd/sharpe + alpha).
- 노출 경로:
  - TUI 스냅샷: `src/agent/steering/runtime.py:publish_snapshot._build()` → `_account_block`(equity/cash/... 노출, 수익률 없음) → `steering/snapshot.json` → TUI 훅.
  - 모바일 대시보드(F86): `operator-console/.../server/autostock/dashboard-read.ts:assembleDashboardPayload` → `GET /autostock/dashboard`. `account.day_pnl_pct`가 현재 `null` 플레이스홀더.

빠져있는 것 (이 트랙의 GAP):
- SPY 일별 가격을 buy-and-hold 곡선으로 **정규화**해 **에이전트 누적수익 vs S&P500 누적수익 + 초과수익(alpha)** 을 계산하는 코드.
- 그 지표를 **매일** TUI/모바일에서 볼 수 있게 노출하는 배선.

무관/제외:
- F70 `src/benchmark/` (dormant, baseline이 지수가 아니라 종목전략) — 재사용 안 함.
- F24/F62 per-decision `benchmark_excess` — per-trade 지표라 포트폴리오 레벨 요청과 다름. 재사용 안 함(별개 지표).

## 확정된 설계 결정 (사용자 답변, 2026-07-10)

| 항목 | 결정 |
|---|---|
| 노출 위치 | **콘솔 TUI + 모바일 대시보드(F86)** (디스크 리포트 파일은 제외) |
| 지표 깊이 | **헤드라인만** — 에이전트 누적수익 %, SPY 누적수익 %, 초과수익(alpha) % |
| 기간 범위 | **누적(시작일 이후) + 오늘 델타**(오늘 에이전트 vs SPY 일간 변화) |
| 품질 확장 | Property-Based Testing = **적용(Full, hypothesis)**; Security Baseline = 미적용 |

## Functional Requirements (기능 요구사항)

- **FR-1 (지표 계산 — 순수 코어)**: `equity.jsonl`의 일별 `(date, equity, benchmark.SPY)` 시계열로부터 다음을 계산하는 순수 함수를 제공한다.
  - **SPY buy-and-hold 정규화**: 시작일(첫 유효 기록일)에 에이전트 시작자본과 동일 금액을 SPY에 전액 투자했다고 가정, `spy_curve[d] = start_equity * SPY[d] / SPY[start]`.
  - **누적수익**: `agent_cum_return = equity[last]/equity[start] - 1`, `spy_cum_return = SPY[last]/SPY[start] - 1`.
  - **초과수익(alpha)**: `alpha = agent_cum_return - spy_cum_return` (단순 누적수익 차, 헤드라인 정의).
  - **오늘 델타**: `agent_day_return = equity[last]/equity[prev] - 1`, `spy_day_return = SPY[last]/SPY[prev] - 1`, `day_alpha = agent_day_return - spy_day_return`. (prev = 직전 유효 기록일)
- **FR-2 (기간/정규화 규칙)**:
  - 시작일 = SPY 값이 존재하는 첫 기록일. (equity.jsonl 초기 라인에 SPY가 비어있을 수 있으므로 첫 유효 SPY 기준.)
  - 두 곡선은 시작일 기준 동일 시작자본으로 정규화(공통 base=100% 또는 동일 금액).
  - **전제**: 계좌 외부 입출금 없음 → 단순 정규화. (입출금 존재 시 입출금 보정으로 확장 여지 — 현재 범위 밖, 가정 명시.)
- **FR-3 (EOD 배선)**: `agent._eod`에서 `record_equity(...)` **직후**(equity.jsonl에 당일 라인이 append된 뒤) 지표를 계산해 스냅샷/steering 아티팩트에 발행한다. 데이터가 부족하면(1개 기록 미만, SPY 없음) 조용히 스킵.
- **FR-4 (TUI 노출)**: 콘솔 TUI에 헤드라인 지표를 표시한다. `steering/snapshot.json`의 account/신규 블록에 `perf_vs_benchmark`(agent_cum, spy_cum, alpha, agent_day, spy_day, day_alpha, since_date) 필드를 추가하고 TUI가 렌더.
- **FR-5 (모바일 대시보드 노출)**: F86 `dashboard-read.ts` 계약에 벤치마크 비교 필드를 추가해 `GET /autostock/dashboard` 응답에 포함. 데이터 없으면 `null`(기존 F86 플레이스홀더 관례 준수). 클라이언트(app addon)가 렌더.
- **FR-6 (백필/온디맨드 조회)**: 데몬 재시작 없이도 현재 `equity.jsonl`로부터 지표를 산출할 수 있는 CLI/함수 진입점을 제공(예: `python -m src.agent.logs.performance` 또는 유사) — 검증·수동 확인용.

## Non-Functional Requirements (비기능 요구사항)

- **NFR-1 (Fail-honest)**: 데이터 부족·SPY 누락·파싱 실패 시 크래시 없이 `None`/생략으로 처리(프로젝트의 fail-honest 관례). EOD 파이프라인을 절대 막지 않음.
- **NFR-2 (순수/결정론)**: 지표 계산은 I/O 없는 순수 함수로 분리(테스트·PBT 대상). 데이터 로딩과 계산 분리.
- **NFR-3 (정확성/PBT)**: 정규화·수익률 계산에 대해 property-based test 적용(불변식: 동일 곡선 입력 시 alpha=0; 시작자본 스케일 불변; SPY==agent일 때 alpha=0; 단조 스케일 불변 등). hypothesis 사용.
- **NFR-4 (성능)**: 하루 1회 EOD 계산 + 스냅샷 발행 시 소량 재계산. equity.jsonl 전체 스캔(수십~수백 라인)로 충분, 무시 가능한 비용.
- **NFR-5 (격리/멀티인스턴스)**: 계좌·workspace 분리 운영(F90/F92) 정합 — 지표는 해당 인스턴스의 `equity.jsonl`만 읽고, 하드코딩 계좌/provider 없음.
- **NFR-6 (기존 계약 호환)**: 스냅샷/대시보드 payload에 필드 **추가만**(기존 필드 제거·rename 없음). TUI/앱 구버전은 새 필드를 무시해도 동작.

## Testable Properties (PBT-01 사전 식별 — Functional Design에서 구체화)

- **불변식(Invariant)**: `agent==spy` 곡선이면 `alpha==0`; 시작자본 배수 스케일링해도 수익률·alpha 불변(range/scale invariance).
- **Oracle**: 소규모 손계산 시계열 vs 함수 출력 일치.
- **Round-trip**: (해당 시) 스냅샷 payload 직렬화/역직렬화 라운드트립 — 노출 계층이 thin이면 N/A 판정.

## Out of Scope (범위 밖)

- 입출금(외부 현금흐름) 보정 수익률 (전제상 제외).
- 디스크 성과 리포트 파일 생성 (사용자 미선택).
- 리스크 지표(Sharpe/MDD/변동성) 표시 (헤드라인만 선택 — 코어 함수는 확장 가능하게 두되 표시는 안 함).
- 롤링(7d/30d) 윈도우 (사용자 미선택).
- 차트/그래프 렌더 (헤드라인 수치만).
- F70 benchmark 러너 활성화.

## Success Criteria (성공 기준)

- 매일 장마감 후 TUI와 모바일 대시보드에서 "에이전트 누적 X% vs S&P500 Y% (alpha Z%)" + 오늘 델타를 확인할 수 있다.
- 지표가 `equity.jsonl`의 실제 값과 일치(수동 손계산 검증 통과).
- 데이터 부족/장애 시에도 EOD 파이프라인과 대시보드가 정상 동작(fail-honest).
- PBT + example 테스트 그린, 실계좌 live smoke 1회 통과.

## Key Requirements Summary

기존에 이미 쌓이는 `equity.jsonl`(일별 equity + SPY)을 조인·정규화하여 **에이전트 누적수익 vs S&P500 누적수익 + alpha + 오늘 델타**(헤드라인)를 계산하고, 이를 **콘솔 TUI와 모바일 대시보드(F86)** 에 매일 노출한다. 순수 코어 함수 + fail-honest 배선 + PBT. 디스크 리포트/리스크지표/롤링/입출금보정은 범위 밖.
