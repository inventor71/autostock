# F80 — Requirements (Parquet 저장 전환)

**Depth**: standard · **Status**: 승인 대기

## 1. 배경 / 의도
사용자 요청: "autostock에서 쓰는 여러 데이터를 jsonl로 저장하는데 parquet로 저장할 만한
것이 있나 보고 시작." → 조사형 요청. 코드베이스 전체 append-only 스토어를 스캔해
Parquet 실익 대상을 선별하고 전환한다.

## 2. 조사 결과 (근거)
- **Parquet 실익이 분명한 유일 대상 = `data/intraday/*.csv` (IntradayFeatureStore)**.
  - `src/data/intraday/store.py` docstring이 명시적으로 swap point로 설계:
    *"a Parquet/DuckDB backend can replace the body later without touching callers."*
  - 컬럼형 수치 피처(22 컬럼, `FEATURE_COLUMNS`), symbol당 1파일, read-all 분석
    (`analysis.py`의 패턴 가설 검정), 운영 누적으로 증가.
  - 현재 CSV 선택 이유는 "pyarrow 부재 회피 + 사람이 읽기 쉽게". → pyarrow 추가하면 해소.
- **약한 후보 (전환 안 함)**: `workspace/*.jsonl` (turns 372K, surge, benchmark, equity,
  trades, signals, screening) — 분석 로그지만 현재 용량 미미(≤372K), 이득 ~0.
- **부적합 (유지)**: steering commands/events, decisions, watch, agent_questions,
  execution_log/outcomes — cross-process IPC / torn-safe 증분 tail-read가 핵심 요건,
  Parquet은 append/부분읽기 불가.

> 정정: 질문은 "JSONL→Parquet"이나 실제 Parquet 적합 대상은 **CSV로 저장 중인 intraday
> store** 하나. 나머지 JSONL은 소용량(이득 없음)이거나 IPC용(전환 불가).

## 3. 확정 범위 (사용자 결정 2026-06-13)
- **전환 대상**: `IntradayFeatureStore` 한 개만.
- **호환성**: **Parquet 단독 + 기존 CSV 1회 마이그레이트** (CSV 폴백 영구 유지 안 함).

## 4. 기능 요구사항
- FR1: `IntradayFeatureStore`의 on-disk 포맷을 symbol당 `<SYMBOL>.parquet`로 변경.
- FR2: 공개 contract(`upsert(records)`, `read(symbols,start,end)`, `symbols()`) **시그니처·반환
  의미 불변** (behavior-preserving). 반환 DataFrame은 기존과 동일 컬럼/순서(`FEATURE_COLUMNS`)·
  동일 정렬·동일 idempotency((date,symbol) last-write-wins).
- FR3: **1회 마이그레이션** — `<SYMBOL>.parquet`이 없고 `<SYMBOL>.csv`가 있으면 read/upsert
  시 CSV를 읽어 parquet로 1회 변환(이후 CSV는 더 이상 기록하지 않음). 변환된 CSV 처리(삭제 vs
  `.migrated` 보존)는 설계 단계에서 확정.

## 5. 비기능 요구사항 (NFR)
- NFR1 (동작 동등성): `date` 컬럼은 문자열로 유지(analysis가 `str(...)`/문자열 정렬/
  drop_duplicates에 의존) — parquet dtype 보존이 기존 CSV round-trip 동작을 바꾸지 않게.
  None/NaN 표현이 read 반환에서 기존과 동등해야 함.
- NFR2 (의존성): `pyarrow`를 `pyproject.toml`에 추가, venv 설치.
- NFR3 (성능): 데이터 소량이라 성능은 부차적; 회귀만 없으면 됨.

## 6. 회귀/검증 기준
- `tests/intraday/test_pattern_detection.py`의 store 테스트(idempotent date, range filter,
  빈 store) 그대로 통과.
- 라운드트립 동등성: upsert한 레코드를 read하면 값/타입이 보존(특히 date 문자열, None).
- 기존 `data/intraday/AAPL.csv` 마이그레이션 스모크(실데이터 1파일).

## 7. 범위 밖
- workspace JSONL 스토어 전환(소용량/IPC) — 미실시.
- DuckDB 쿼리 레이어, 파티셔닝, 압축 코덱 튜닝 — 미실시(단순 to_parquet/read_parquet).
