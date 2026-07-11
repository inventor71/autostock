# F97 Functional Design — perf-vs-benchmark 유닛

## 설계 요지 (핵심 단순화)

성과 지표는 **read-time 파생**으로 만든다. 이미 EOD마다 `record_equity`가
`equity.jsonl`에 `{date, equity, benchmark.SPY}`를 쓰므로, 새 EOD 훅을 추가하지 않고
**스냅샷 발행/CLI 시점에 `equity.jsonl`을 읽어 계산**한다.

- 장점: `agent._eod` 미변경(파이프라인 커플링·머지리스크↓), 항상 최신값, fail-honest by construction(파일 없으면 None).
- 비용: 스냅샷 발행마다 소형 JSONL(수십~수백 줄) 1회 읽기 — 무시 가능.

## 컴포넌트 1 — Python 순수 코어 (신규): `src/agent/logs/performance.py`

### 1.1 자료 (파생, 영속 스키마 아님)
```
PerfVsBenchmark (dict, JSON 직렬화 가능):
  since_date:       str    # 기준일(첫 usable 기록의 date)
  days:             int    # usable 기록 수
  agent_return_pct: float  # 시작일 이후 누적수익 %, round(2)
  spy_return_pct:   float  # SPY buy-and-hold 누적수익 %, round(2)
  alpha_pct:        float  # agent_return_pct - spy_return_pct (누적 초과수익)
  agent_day_pct:    float|None  # 오늘(마지막 vs 직전 usable) 일간수익 %
  spy_day_pct:      float|None  # SPY 일간수익 %
  day_alpha_pct:    float|None  # agent_day_pct - spy_day_pct
```

### 1.2 함수 시그니처
```python
def compute_performance(
    records: list[dict],
    *,
    benchmark_key: str = "SPY",
) -> dict | None:
    """equity.jsonl 레코드에서 에이전트 vs SPY buy-and-hold 성과를 계산.
    데이터 부족/파싱불가 → None (fail-honest). I/O 없음(순수)."""
```

보조:
```python
def load_performance(path: str | Path | None = None) -> dict | None:
    """default equity.jsonl(또는 지정 경로)을 읽어 compute_performance() 반환.
    read_equity() 재사용. 예외 시 None."""
```

### 1.3 알고리즘 (정확 정의)
1. **usable 필터**: 각 record에서 `equity`(float, >0)와 `benchmark.SPY`(float, >0)가
   모두 존재하는 것만 취한다. 순서 보존(파일은 oldest-first). 파싱 불가 값은 스킵.
   - `benchmark`는 `record.get("benchmark") or {}`, SPY는 `benchmark.get("SPY")`.
   - 초기 라인이 SPY 없이 기록된 경우(관측됨) 자동 제외 → **기준일 = SPY 있는 첫 날**.
2. usable가 **0개** → `None`.
3. `base = usable[0]`, `last = usable[-1]`.
   - `agent_return_pct = (last.equity / base.equity - 1) * 100`
   - `spy_return_pct   = (last.SPY   / base.SPY   - 1) * 100`
   - `alpha_pct        = agent_return_pct - spy_return_pct`
   - `since_date = base["date"]`, `days = len(usable)`
   - usable가 1개면 세 값 모두 0.0 (base==last).
4. **오늘 델타**: usable ≥ 2이면 `prev = usable[-2]`:
   - `agent_day_pct = (last.equity / prev.equity - 1) * 100`
   - `spy_day_pct   = (last.SPY   / prev.SPY   - 1) * 100`
   - `day_alpha_pct = agent_day_pct - spy_day_pct`
   - usable < 2이면 세 필드 = `None`.
5. 모든 float는 `round(x, 2)`. 0 나눗셈은 필터(>0)로 원천 차단.

**정규화 해석**: "같은 돈을 SPY에 그냥 넣었다면"과 정확히 일치 —
누적수익은 시작가 대비 비율이라 시작자본 금액에 무관(스케일 불변). 별도 시작자본 상수 불필요.

### 1.4 CLI 진입점 (FR-6, 검증용)
```python
def main() -> None:
    """python -m src.agent.logs.performance
    default equity.jsonl에서 헤드라인 출력(에이전트/SPY/alpha/오늘델타)."""
```
데이터 없으면 "성과 데이터 부족" 류 메시지 후 정상 종료(비크래시).

## 컴포넌트 2 — 스냅샷 배선: `src/agent/steering/runtime.py`

`publish_snapshot._build()`의 snapshot dict에 필드 **추가만**:
```python
"perf_vs_benchmark": self._perf_block(),   # F97 (read-time 파생, additive)
```
신규 메서드:
```python
def _perf_block(self) -> dict | None:
    """equity.jsonl에서 성과 헤드라인 파생. 실패/부족 → None (스냅샷을 막지 않음)."""
    try:
        from src.agent.logs.performance import load_performance
        return load_performance(self.executor.journal.root / "equity.jsonl")
    except Exception:
        return None
```
- `_account_block`(static, ps만 받음)과 별도. 파일 기반이므로 broker 접근 불필요.
- 예외는 삼켜서 `None` → 기존 스냅샷 계약 100% 하위호환(구 리더는 새 키 무시).

## 컴포넌트 3 — 모바일 대시보드(F86): `dashboard-read.ts`

`DashboardPayload`에 `perf` 필드 추가(있으면 값, 없으면 null — F86 관례):
```ts
perf: {
  since_date: string | null
  agent_return_pct: number | null
  spy_return_pct: number | null
  alpha_pct: number | null
  agent_day_pct: number | null
  spy_day_pct: number | null
  day_alpha_pct: number | null
} | null
```
`assembleDashboardPayload`에서 `snapshot.perf_vs_benchmark`를 방어적으로 읽어 매핑
(`isObj`/`num`/`str` 기존 헬퍼 재사용). 없으면 `perf: null`. `EMPTY_PAYLOAD.perf = null`.

## 컴포넌트 4 — 렌더 (콘솔 TUI + 모바일)

공유 `DashboardView`(F79 C6)로 양 surface가 수렴. 헤드라인 한 줄 추가:
> **vs S&P500**: 에이전트 +3.42% · SPY +1.10% · **α +2.32%** (오늘 +0.31%p, 05-28~)

- **모바일**: `dashboard-source.ts`가 서버 `perf`를 `DashboardView` 모델로 매핑 →
  `dashboard-view.tsx`에 성과 라인 렌더. `perf==null`이면 라인 숨김/"—".
- **콘솔 TUI**: TUI account/스냅샷 소스가 `snapshot.perf_vs_benchmark`를 읽어 동일 헤드라인 표시.
- 색상: alpha ≥ 0 초록 / < 0 빨강 (기존 pnl 색 관례 재사용). 값 없으면 회색 "—".
- **정확한 렌더 지점/컴포넌트는 코드생성 단계에서 F86/F79 DashboardView 경로를 따라 배선**
  (focused 서브에이전트로 TS 렌더 사이트 확인 후 최소 침습 추가).

## Testable Properties (PBT-01)

| # | 범주 | Property |
|---|---|---|
| P1 | Invariant (scale) | 모든 `equity`에 상수 k>0 곱해도 `agent_return_pct` 불변; 모든 SPY에 곱해도 `spy_return_pct` 불변 |
| P2 | Invariant (zero-alpha) | `equity[i] = c * SPY[i]` (c>0 상수)면 `alpha_pct == 0` 이고 `agent==spy` (부동소수 허용오차) |
| P3 | Oracle | 소규모 손계산 시계열 == 함수 출력 |
| P4 | Invariant (consistency) | 항상 `alpha_pct == agent_return_pct - spy_return_pct` (그리고 day_alpha 동일) |
| P5 | Robustness | SPY 없는/0/비수치 record를 임의 삽입해도 결과 불변(필터링) |
| P6 | Boundary | usable 0 → None; usable 1 → 누적 0.0·day None; usable ≥2 → day 값 존재 |

- 생성기(PBT-07): 도메인 생성기 — 양의 float equity/SPY 시계열(현실 범위), 선택적으로 SPY 결측 record 주입.
- 프레임워크(PBT-09): **hypothesis** (repo 기존 사용). shrinking/seed 기본(PBT-08).
- 노출 계층(runtime `_perf_block`, TS 매핑)은 thin passthrough → **PBT N/A**(example 테스트로 커버). PBT-10: 핵심 경로에 example 테스트 병행.

## Fail-honest / 호환 (NFR)
- 코어·배선 모든 실패 경로 → `None`/생략, 예외 전파 없음. EOD·스냅샷·대시보드 절대 안 막음.
- payload는 additive only(제거·rename 없음) → 구버전 TUI/앱 무시해도 동작.
- 멀티인스턴스: 해당 인스턴스 `journal.root/equity.jsonl`만 읽음(하드코딩 계좌/provider 없음).

## 손대는 파일 (요약)
1. `src/agent/logs/performance.py` (신규)
2. `src/agent/steering/runtime.py` (+`_perf_block`, snapshot dict 1줄)
3. `operator-console/.../server/autostock/dashboard-read.ts` (+`perf` 필드/매핑)
4. `operator-console/.../app/src/addons/autostock/` dashboard-source.ts + dashboard-view.tsx (+TUI 소스) — 렌더
5. 테스트: `tests/.../test_performance.py` (PBT+example), TS 테스트 확장

**미변경**: `agent.py:_eod`, `equity.py`(read_equity만 재사용), `src/benchmark/`(무관).
