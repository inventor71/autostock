# F77 / Unit "stocktwits-sentiment" — Functional Design

**Date**: 2026-06-13 · **Base**: requirements.md + workflow-plan.md (승인)

## 1. 데이터 설계

### 1.1 히스토리 파일 — `workspace/sentiment/<ET날짜>.jsonl` (append-only)

스윕 1회당 심볼별 한 줄 (F72 screening 선례: ET 날짜 키, gitignored workspace):

```json
{"ts": "2026-06-13T10:00:05-04:00", "symbol": "NVDA", "bullish_n": 21, "bearish_n": 4, "untagged_n": 5, "latest_id": 612345678}
```

- `*_n`은 해당 시점 스트림 최근 30개 메시지 내 집계 (스냅샷 — 누적 아님).
- `latest_id`: 최신 메시지 id (다음 스윕에서 변화량=신규 글 추정의 근거,
  메시지량 z-score의 입력).
- **저장 금지**: 사용자명, 본문, 링크 (NFR-4 / SECURITY-03).

### 1.2 설정 — `settings.yaml` `signals.sentiment:` 블록 (FR-7 선례)

```yaml
signals:
  sentiment:
    enabled: true
    sweep_minutes: 60          # 스윕 주기
    window_et: ["04:00", "20:00"]  # 스윕 시간 창 (ET)
    request_gap_s: 0.5         # 심볼 간 간격 (131심볼 × 0.5s ≈ 66s/스윕)
    hourly_budget: 150         # 시간당 요청 상한 (NFR-3)
    baseline_days: 5           # 베이스라인 윈도
    min_baseline_points: 12    # 콜드스타트 컷 (이 미만이면 이상치 후보 제외)
    min_tagged: 8              # 현재 스냅샷 태그 수 최소 (소표본 노이즈 컷)
    top_k: 5                   # 브리프 이상치 최대 수
    z_threshold: 2.0           # |z| 임계 (ratio 또는 volume)
```

`SignalsConfig`에 `sentiment: SentimentConfig` 서브모델 추가 (기본값으로 빈 블록 동작).

## 2. 컴포넌트 설계

### 2.1 소스 — `src/signals/sources/stocktwits.py`

```python
_BASE_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"

class StocktwitsSource:
    def __init__(self, *, http_connect_timeout=3.0, http_read_timeout=5.0): ...
    def fetch_symbol(self, symbol: str) -> SentimentSnapshot:
        # GET → resp.raise_for_status() → pydantic 파싱(관대: 필요한 필드만)
        # messages[].entities.sentiment.basic ∈ {"Bullish","Bearish",None}
        # → SentimentSnapshot(symbol, bullish_n, bearish_n, untagged_n, latest_id)
        # 429/403 → RateLimited 예외 (스윕 루프가 백오프)
```

- finnhub_earnings 패턴 준수: requests 지역 import, transport 오류는 raise —
  **호출자(스윕 러너/collector)가 degrade 판단**.
- 응답 검증: 숫자/문자 타입 체크, 심볼 정규화(upper), 예상 밖 구조는 해당
  메시지 skip (SECURITY-05).

### 2.2 스토어+코어 — `src/signals/sentiment.py` (신규 1파일: 순수 코어 + 얇은 I/O)

```python
# 순수 (PBT 대상)
def aggregate_labels(messages: list[dict]) -> tuple[int, int, int]   # bull/bear/untagged
def bull_ratio(bullish_n, bearish_n) -> float | None                 # 태그 0이면 None
def baseline(history: list[SentimentRecord]) -> Baseline             # 평균/표준편차 (ratio, tagged_n)
def zscores(current, baseline) -> tuple[float|None, float|None]      # ratio_z, volume_z
def select_outliers(currents, baselines, cfg) -> list[SentimentOutlier]
    # |z|≥threshold, min_baseline_points·min_tagged 충족, |z| 내림차순 top_k

# I/O (fail-honest)
def append_sweep(records, root=None, ts=None) -> Path | None         # JSONL append (atomic-enough O_APPEND)
def load_recent(root, days) -> dict[symbol, list[SentimentRecord]]   # 최근 N일 파일만 read, 손상 행 skip
```

- z-score: 표준편차 0/None → z=None (이상치 불가) — 0-division 금지.
- 베이스라인 포인트 = 과거 스윕 레코드 1개. `min_baseline_points=12` ≈ 하루치.

### 2.3 스윕 러너 — `src/signals/sentiment_sweep.py` (데몬 잡 본체)

```python
class SentimentSweeper:
    def __init__(self, *, source, universe, cfg, root=None, now_fn=None): ...
    def sweep_tick(self) -> None:
        # 1) enabled + ET 시간 창 체크 (아니면 no-op)
        # 2) 심볼 순회: fetch → 실패 심볼 skip(카운트), RateLimited → 즉시 중단(백오프 로그)
        #    요청 간 request_gap_s 슬립, 누적 요청 hourly_budget 도달 시 중단
        # 3) append_sweep() — 부분 결과도 저장 (수집된 만큼)
        # 4) 요약 로그 1줄 (ok/skip/aborted 카운트)
        # 전체 try-except: 어떤 예외도 스케줄러로 전파 금지 (NFR-1)
```

- 등록: `src/trading/modes/agent.py`에
  `scheduler.add_seconds_job(sweeper.sweep_tick, cfg.sweep_minutes*60, "sentiment_sweep")`
  (enabled일 때만). 시간 창 판정은 tick 내부 — 스케줄러는 단순 주기.

### 2.4 브리프 통합 — `collector.py` + `brief.py` + `records.py`

- `records.py`: `SentimentOutlier(symbol, bull_ratio, ratio_z, tagged_n, volume_z, direction)`
  추가, `MarketSignalBrief.sentiment_outliers: list[SentimentOutlier]` 필드 +
  `is_empty()`에 포함.
- `collector.collect()`: `load_recent` → `select_outliers` (히스토리 read만,
  HTTP 없음 — 스윕이 이미 모아둠). 실패 → `degraded.append("sentiment:history")`.
  히스토리 자체가 없으면(스윕 미가동/콜드스타트) 조용히 빈 목록 — degraded 아님.
- `brief.to_prompt_text()` 렌더:

```text
Retail sentiment (StockTwits, self-labeled — vs own baseline):
  - NVDA bull 45% (z=-2.7, usually ~78%), msgs x3.1 (z=+2.9) — bearish shift on rising chatter
  - TMO bull 92% (z=+2.2), msgs x1.0 — bullish skew, low volume
```

- intraday(F3 BriefAssembler): 보유/워치 심볼 ∩ 이상치만 한 줄 추가 —
  기존 brief 조립 인터페이스에 선택 섹션으로 (이상치 없으면 무출력).

## 3. 오류 경로 매트릭스 (NFR-1/3, SECURITY-15)

| 상황 | 동작 |
|---|---|
| 심볼 1개 HTTP 실패/형식 변화 | 해당 심볼 skip, 스윕 계속 |
| 429/403 (차단/한도) | 스윕 즉시 중단 + 경고 로그, 부분 결과 저장, 다음 주기 재시도 |
| 시간당 예산 도달 | 위와 동일 (중단·저장) |
| 히스토리 파일 손상 행 | skip (관대 파싱, F72 선례) |
| 히스토리 없음 (콜드스타트) | 브리프 섹션 생략, degraded 아님 |
| load/select 예외 | `degraded_sources=["sentiment:history"]`, 턴 정상 |
| 스윕 러너 임의 예외 | tick 내 흡수, 스케줄러 무사 (기존 wake detector 패턴) |

## 4. 테스트 설계 (PBT Partial)

**순수 코어 (`tests/signals/test_sentiment.py`)**:
- PBT(hypothesis): ① `aggregate_labels` — 임의 메시지 리스트에서 bull+bear+untagged
  = len 불변식, ② `bull_ratio` ∈ [0,1] 또는 None, ③ `zscores` — std=0/표본부족 →
  None(예외 없음), ④ 레코드 직렬화 round-trip.
- 예제: select_outliers 컷 규칙(min_points/min_tagged/top_k/내림차순), 베이스라인 수치.

**소스/스윕**: 가짜 HTTP(고정 JSON 픽스처 — 실제 응답 형태 축약본)로 파싱·라벨 집계,
429 → RateLimited, 예산 도달 중단, 시간 창 밖 no-op, 부분 저장. 요청 수 카운트 ≤ 예산
(수용기준 4).

**브리프**: 이상치 유/무/degraded 각각의 렌더 출력, intraday 교집합 필터.

**라이브 스모크 (Build & Test)**: 실제 StockTwits로 5~10심볼 미니 스윕 → JSONL 확인 →
합성 히스토리 섞어 select_outliers → 브리프 텍스트 렌더까지.
