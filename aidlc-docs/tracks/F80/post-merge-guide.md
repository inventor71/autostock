# F80 — Post-Merge Guide (Parquet 전환)

## 무엇이 바뀌나
- `IntradayFeatureStore`(intraday 피처 누적 스토어)의 on-disk 포맷이 **CSV → Parquet**로 바뀜.
  파일은 `data/intraday/<SYMBOL>.parquet` (gitignored). 공개 API(`upsert`/`read`/`symbols`)는
  동일 — collector/analysis 등 호출부 변경 없음.
- 새 의존성 **pyarrow** 추가.

## 전제조건 (머지 후 1회)
```bash
pip install -e .     # pyarrow 설치 (또는: pip install "pyarrow>=14.0.0")
```
- 데몬을 돌리는 환경이면 재시작 시 venv에 pyarrow가 있어야 함. docker-verify/CI 이미지도
  재빌드 시 자동 포함(pyproject 반영).

## 자동 마이그레이션 (조치 불필요)
- 기존 `data/intraday/*.csv`가 있으면 **첫 read/upsert/symbols 호출 시 1회 자동 변환**됨:
  `<SYMBOL>.csv` → `<SYMBOL>.parquet` 생성, 원본은 `<SYMBOL>.csv.migrated`로 rename(보존).
- 데이터 손실 없음. 변환이 잘 됐는지 확인 후 `.csv.migrated`는 수동 삭제 가능(선택).

## 실사용 검증 체크리스트
1. `pip install -e .` 후 `python -c "import pyarrow; print(pyarrow.__version__)"` → 버전 출력.
2. (기존 데이터가 있으면) intraday collector 1회 실행 또는:
   ```bash
   python -c "from src.data.intraday.store import IntradayFeatureStore as S; s=S(); print(s.symbols()); print(len(s.read()))"
   ```
   → `data/intraday/`에 `*.parquet` 생성, `*.csv`는 `*.csv.migrated`로 바뀜, 행 수가 기존과 동일.
3. `python -m src.data.intraday.analysis` → 패턴 분석 리포트가 정상 출력(빈 데이터면 빈 리포트).
4. "정상" 모습: read()가 기존과 동일 컬럼/행/값 반환, 날짜는 `YYYY-MM-DD` 문자열 유지.

## 롤백
- 코드 롤백: 이 트랙 커밋 revert. 단, 그 사이 생성된 `*.parquet`는 구버전 코드가 못 읽음 →
  `*.csv.migrated`를 `*.csv`로 되돌리면 구버전 CSV 백엔드가 다시 읽음(데이터 보존됨).

## 알려진 한계 / 범위 밖
- workspace의 다른 JSONL 스토어(turns/surge/benchmark/equity 등)는 전환 대상 아님(소용량/IPC).
- DuckDB 쿼리 레이어·파티셔닝·압축 코덱 튜닝은 미적용(단순 to_parquet/read_parquet).
