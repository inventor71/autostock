# Stage 3 — Redesign: 레이아웃 + 매핑

**Track**: R10 · **Date**: 2026-06-11

## 새 레이아웃
```
src/data/intraday/
├── __init__.py      # 패키지 docstring: 역할 경계 명시 (수집·피처·저장 ↔ agent/intraday=의사결정 루프)
├── features.py      # ← intraday_features.py
├── store.py         # ← intraday_store.py
├── collector.py     # ← intraday_collector.py  (-m CLI: python -m src.data.intraday.collector)
└── analysis.py      # ← intraday_analysis.py   (-m CLI: python -m src.data.intraday.analysis)
```

## 결정
1. **심볼 개명 없음** — Stage 1 검토 결과 모듈-접두 stutter인 심볼이 없음 (`IntradayFeatureStore` 유지).
2. **`__init__.py`는 빈 재export 없이 docstring만** — monorepo-native(shim 금지) 원칙. 호출부는
   풀 경로(`src.data.intraday.store`)로 직접 import.
3. **`-m` 경로 클린 브레이크** — argparse `prog=` + 모듈 docstring 예시를 새 경로로. 옛 경로 호환 없음
   (기결정). post-merge-guide에 옛→새 경로 표 수록.
4. **CSV 데이터 디렉터리 `data/intraday/`(파일시스템)는 불변** — 모듈 경로와 별개. store 기본 root 유지.

## 마이그레이션 순서 (Stage 4)
1. 기존 테스트 green 확인 → 2. `git mv` ×4 + `__init__.py` → 3. 내부 import/argparse/docstring 갱신
→ 4. `runtime.py:563` 문자열 → 5. `tests/test_intraday.py` import → 6. 전체 스위트 + `-m --help` 스모크.
