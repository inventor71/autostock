# Tier Ledger — R9 config↔settings 용어 통일

범위: `src/benchmark/config.py` + `src/early_session/config.py` → `settings.py` (구조점검 #3)
작성일: 2026-06-09

## T1 — 동작 보존 (자율 진행)
| # | 변경 항목 | 보존되는 동작 | 보존 검증 방식 | 근거 |
|---|-----------|---------------|----------------|------|
| 1 | `src/benchmark/config.py` → `src/benchmark/settings.py` (`git mv`) | `BenchmarkConfig` 공개 API + `DEFAULT_BASELINES` 값 동일 | 기존 `tests/benchmark/test_config.py` + `test_runner.py` (green) | 클래스/상수 내용 불변, 파일 위치만 이동 |
| 2 | `src/early_session/config.py` → `src/early_session/settings.py` (`git mv`) | `EarlySessionConfig` 공개 API + `effective_retention_minutes` 등 동일 | 기존 `tests/test_early_session.py` + `test_f56_bugfixes.py` (green) | 동일 |
| 3 | import 경로 **10곳** `…config`→`…settings` 갱신 (main.py:512 포함) | import 결과 동일 객체 | 위 테스트 import + **벤치마크 라이브 스모크**(main.py 경로는 테스트 미커버) | Python 모듈=파일, 경로만 변경 |
| 4 | `src/early_session/settings.py:4` docstring 자기참조 `config.py`→`settings.py` | (주석) | n/a | 정합성 |
| 5 | `tests/benchmark/test_config.py` → `tests/benchmark/test_settings.py` | 테스트 내용 동일 | 수집 수 동일·green | 개명 모듈을 native하게 미러(트랙ID 테스트 아님; R13 범위 밖) |

## T2 — 안전한 확장 (자율 진행 + 사후 보고)
없음.

## T3 — 의도 변경 / 기능 cut (🛑 승인 필요)
없음. — 외부 표면(동적 import·`-m`·YAML 키) 0건(Stage 1 sweep). 클래스명·기본값·YAML 섹션키 전부 불변.

## 정지 지점
- [x] T3 항목 없음 — 게이트 불필요
- [x] 모든 T1 항목이 기존 특성화 테스트로 보호됨(공백 없음)

## import 사이트 (전수, repo-wide sweep — critic 정정)
benchmark.config(4): `src/benchmark/runner.py:10`, **`main.py:512`(지연 import, 테스트 미커버)**,
`tests/benchmark/test_runner.py:10`, `tests/benchmark/test_config.py:3`
early_session.config(6): `src/early_session/__init__.py:6`, `src/early_session/monitor.py:24`,
`src/trading/modes/agent.py:292`, `tests/test_early_session.py:18`, `tests/test_f56_bugfixes.py:181,234`
doc(1): `src/early_session/config.py:4`
