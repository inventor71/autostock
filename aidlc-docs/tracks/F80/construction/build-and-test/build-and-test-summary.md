# F80 — Build & Test Summary

**대상**: `IntradayFeatureStore` CSV → Parquet 전환 (behavior-preserving) + pyarrow 의존성.

## 변경 파일
- `src/data/intraday/store.py` — backend CSV→Parquet, `_path` `.parquet`, `_migrate_legacy()`
  (1회 CSV→Parquet 변환 + 원본 `.csv.migrated` 보존), `read`/`upsert`/`symbols`에서 lazy 호출.
  공개 contract(시그니처/반환 의미) 불변.
- `pyproject.toml` — `pyarrow>=14.0.0` 추가.
- `tests/intraday/test_pattern_detection.py` — Parquet 영속/마이그레이션/PBT 테스트 추가.

## 빌드 / 의존성
```bash
pip install -e .            # 또는: pip install "pyarrow>=14.0.0"
```
설치된 버전: pyarrow 24.0.0 (cp312).

## 테스트 실행
```bash
python -m pytest tests/intraday/test_pattern_detection.py -q
```

## 결과 (ALL GREEN — 대상 범위)
- `tests/intraday/test_pattern_detection.py`: **23 passed** (기존 + 신규).
  - 기존 store contract 테스트(roundtrip/idempotency, filters/multi-symbol, empty) — 그대로 통과.
  - 신규: `test_persists_as_parquet_not_csv`, `TestStoreLegacyMigration`(3건),
    `TestStoreProperties`(PBT round-trip + idempotence).
- **실데이터 마이그레이션 스모크**: 실제 `data/intraday/AAPL.csv`(647행) → Parquet 변환,
  CSV↔Parquet 값 대조 **0 mismatch**, `date` 컬럼 문자열 보존, 원본 `.csv.migrated`로 보존.

## 전체 스위트 비고 (F80 비유발)
`python -m pytest tests/ -q` → **1244 passed, 4 failed**. 4건 모두 F80 무관:
- `tests/signals/test_sentiment_sweep.py` (3) — base main(01ced61)에서도 동일 실패(선존).
- `tests/test_health_publish.py::test_publish_resolves_repo_root_not_above_it` (1) —
  worktree에서만 실패(메인 통과). worktree에 gitignored `.env`/`settings.yaml` 부재로 인한
  환경 아티팩트(config_env=ERROR). F80 diff와 무관(store/pyproject/test 3파일만 변경).

## PBT Findings
없음. 적용 property(round-trip / idempotence / column-invariant) 모두 통과. (PBT-06 stateful N/A)

## Extension Compliance
- Security Baseline: Disabled (N/A — gitignored 비민감 시장 피처, 외부입력/자격증명 경계 없음).
- Property-Based Testing: Enabled(Full) — 준수(위 PBT Findings).
