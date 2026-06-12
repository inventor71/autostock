# R13 단계 1 — Baseline (tests 네이밍/구조)

## 보존 불변식 (관측 가능 동작)
- **pytest 수집 수 = 1087** (`python -m pytest tests/ --co -q` 기준). 리네임/이동 후 동일해야 함.
- **전체 green** 유지.
- 테스트 **내용·로직 불변** — 파일명/함수·클래스명/위치만 변경.

## 현재 구조
- `tests/` 평면 74개 + 서브디렉터리 3개(`benchmark/` `signals/` `refactor/`, 각 `__init__.py` 有).
- 루트 `tests/conftest.py` **없음**(signals/만 자체 conftest). 상호 test import **없음**.

## 특성화(characterization) 테스트
- 본 트랙은 **테스트 자체를 옮기는** 작업이라 새 특성화 테스트 불요.
  안전망 = **수집 수(1087) 동일 + 전체 green** (before/after 비교). red·count 변화 = T3 신호 → 정지.

## 안전성 전수검사 결과 (이동/리네임이 깨뜨리는지)
- 테스트 파일 간 상호 import: **0** (`grep 'from tests\.|from test_'`).
- CI/`pyproject`/`-k`/`Makefile`의 테스트 파일명 참조: **0**.
- 문서(*.md)의 해당 파일명 참조: **0**.
→ 리네임·이동이 수집·import·CI·문서 어느 것도 깨지 않음.

## 정비 대상
- **트랙ID 기반 파일명 9개**: test_f14 / test_f56_bugfixes / test_f69_health_publish /
  test_monitor_f22 / test_sidebar_status_rich / test_sidebar_upgrade / test_timeline_f25 /
  test_turn_dedup_f44 / test_turn_log_f22.
- **F-번호 함수/클래스명**: `test_..._f54_parity`(test_short_etb_gate.py), `TestEarlySessionMonitorF56`(test_f56).
- **구조 그룹화 후보**: intraday 13, kis 4, surge 3 (src 패키지 미러).
