# F82 — Requirements (Intraday 자동 수집)

**Depth**: standard · **의존**: F80 (Parquet store, stacked) · **Status**: 승인 대기

## 1. 배경
intraday feature store(`data/intraday/*.parquet`)는 현재 **수동 CLI(`collector`)로만** 채워지며
프로덕션 미배선 → AAPL 1종목·17일 stale. 패턴분석(`analysis.py`)·향후 학습이 의미 있으려면
유니버스 전체가 자동으로 쌓여야 한다.

## 2. 확정 결정 (UAQ 2026-06-14)
- 백필 깊이: **2~3년** (기본 3년).
- 압축: **snappy 기본** (F80과 동일, 코드 변경 0).
- 자동화 범위: **EOD append + 데몬 기동 시 자동 갭 백필** (완전 무인).

## 3. 기능 요구사항
- **FR1 (EOD append)**: 미국 장마감 직후 유니버스 전체의 그날 세션 피처를 수집해 store에 upsert.
  기존 `_eod()` 사이클에 best-effort로 추가(실패해도 데몬·EOD 리뷰 비차단).
- **FR2 (갭 인지 백필)**: 데몬 기동 시 유니버스 각 종목의 store 커버리지를 확인해 **부족분만** 백필:
  - 데이터 없음 → `now - backfill_years` ~ `now` 전체 백필.
  - stale → `last_date+1` ~ `now`만 백필.
  - 최신 → skip.
- **FR3 (논블로킹)**: 백필은 **백그라운드 스레드**로 실행 — 다년치×~100종목이 데몬 startup을
  막지 않게. 진행/결과는 로그로 관측.
- **FR4 (설정 게이트)**: `settings.yaml`에 `intraday_collection` 블록.
  키: `enabled`(기본 **false**), `backfill_years`(기본 3), `provider`(기본 alpaca),
  `timeframe`(기본 5m). disabled면 미배선.
- **FR5 (provider)**: 백필은 깊은 히스토리가 필요하므로 alpaca 레인지 페치 사용. EOD today는
  데몬의 기존 `executor.data_provider` 재사용. provider가 yfinance면 백필은 ~60일로 자연
  degrade(경고 로그) — 크래시 금지.

## 4. 비기능 요구사항
- **NFR1 (fail-closed)**: 수집/백필의 어떤 예외도 데몬을 죽이거나 EOD 트레이딩 사이클을
  중단시키지 않음(종목 단위 격리는 `collect()`가 이미 보장).
- **NFR2 (멱등)**: 같은 날 EOD 중복 실행돼도 `(date,symbol)` last-write-wins라 무중복.
  재시작 후 백필도 이미 있는 범위는 skip.
- **NFR3 (throughput)**: alpaca 1심볼=1 range 요청, ~100종목 순차 수분 내. 백그라운드라
  startup 무영향. (병렬화 범위 밖.)
- **NFR4 (용량)**: 실측 3년 ~12MB, ~4MB/년. 관리 불필요.

## 5. 검증 기준
- 갭검출: 빈 store→전체, stale→증분, 최신→skip (fake provider/store).
- EOD append: today 경로 수집→upsert, 부분 실패 격리.
- 설정 게이트: enabled=false면 잡/스레드 미생성.
- fail-closed: provider 예외 시 데몬 start/_eod 정상 진행.

## 6. 범위 밖
- 백필 병렬화/리트라이 백오프 정교화.
- 분봉 원본(raw bars) 저장 — 피처(세션 요약)만.
- KR(KIS) intraday 수집 — 본 트랙은 US.
- store 쓰기 경로 최적화(파일 통째 rewrite) — 현 규모 불필요.
