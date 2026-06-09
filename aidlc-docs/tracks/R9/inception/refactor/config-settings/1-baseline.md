# R9 Stage 1 — Baseline + 특성화 (config↔settings 용어 통일)

범위: 패키지 로컬 설정 모듈명 `config.py` → `settings.py` 통일 (구조점검 #3)
작성일: 2026-06-09 · Base: `3297de5` · Branch: `refactor/R9` · Worktree: `.claude/worktrees/R9`

## 현재 구조

같은 개념("패키지 로컬 설정 모델")이 두 모듈명으로 갈려 있다:

| 패키지 | 현재 모듈 | 클래스 | 종류 |
|--------|-----------|--------|------|
| benchmark | `src/benchmark/config.py` | `BenchmarkConfig` (+ `DEFAULT_BASELINES`) | `@dataclass` |
| early_session | `src/early_session/config.py` | `EarlySessionConfig` | pydantic `BaseModel` |
| signals | `src/signals/settings.py` | `SignalsConfig`, `SignalSources` | pydantic |
| surge | `src/surge/settings.py` | `SurgeDetectionConfig` | pydantic |
| agent/intraday | `src/agent/intraday/settings.py` | `IntradayConfig` | dataclass |

**관찰**: 이미 다수가 `settings.py`이고, 그 안의 클래스는 `*Config`로 명명돼 있다
(`SignalsConfig`/`SurgeDetectionConfig`/`IntradayConfig`). 즉 **확립된 관례 = 모듈 `settings.py`
+ 클래스 `*Config`**. benchmark/early_session의 클래스명(`BenchmarkConfig`/`EarlySessionConfig`)은
**이미 그 관례를 따른다** → 클래스명은 손댈 필요 없고, **모듈 파일명만** 어긋나 있다.

전역 설정은 별개: repo-root `config/config.py`의 `get_settings()`(`from config.config import ...`,
20+ 사이트). 이건 "전역=config" 역할이므로 **유지**(로컬=settings 와 의미 분리).

## 보존해야 할 관측 가능 동작 (외부 계약)

R9는 **모듈 파일명만** 바꾼다. 다음은 전부 불변(byte-for-byte):
- `BenchmarkConfig` / `EarlySessionConfig`의 공개 API(필드·기본값·`from_settings`·`effective_retention_minutes` 등 프로퍼티).
- `DEFAULT_BASELINES` 값.
- `config/settings.yaml`의 섹션 키(`benchmark:`, `early_session:`) — 이건 **YAML 블록명**이지
  모듈 경로가 아니다(`getattr(settings, "benchmark")`로 읽음). **모듈 개명과 무관 → 불변.**
- 설정 파싱 동작·검증·에러.
- **변경되는 유일한 것**: import 경로 `…config` → `…settings` (코드 내부 식별자, 외부 표면 아님).

## 변경 영향 인벤토리 (전수검사 — `rg` 확정)

import 사이트 **10곳** + 모듈 내 doc 자기참조 1곳:
(주의 — sweep은 **repo-wide**로: `rg … --glob '!aidlc-docs/**'`. 초기 `src tests` 스코프는
repo-루트 `main.py`를 놓쳤다 — critic이 잡은 HIGH. 아래는 정정된 전수 목록.)

**benchmark.config (4):**
- `src/benchmark/runner.py:10`
- `main.py:512` ← **지연 import**(`_maybe_start_benchmark`, `try/except`로 감쌈). 누락 시 ImportError가
  삼켜져 **F70 벤치마크가 조용히 비활성화**되고 어떤 테스트도 못 잡는다 → 반드시 갱신.
- `tests/benchmark/test_runner.py:10`
- `tests/benchmark/test_config.py:3`  ← 파일명도 `test_config.py` (Stage 3에서 `test_settings.py` 동반 개명 검토)

**early_session.config (6):**
- `src/early_session/__init__.py:6`
- `src/early_session/monitor.py:24`
- `src/trading/modes/agent.py:292` (지연 import)
- `tests/test_early_session.py:18`
- `tests/test_f56_bugfixes.py:181`, `:234`

**doc 자기참조 (1):**
- `src/early_session/config.py:4` — docstring "See ``src/early_session/config.py`` in the F51 design."
  → 새 경로로 갱신.

**외부 표면**: 없음. 동적 import / `__import__` / `python -m …config` / 직렬화된 모듈경로
참조 **0건**(sweep 확인). → R9는 **순수 T1, 클린브레이크·post-merge-guide 불필요**.

## 특성화 테스트 (before/after green 안전망)

두 클래스 모두 **기존 테스트가 이미 커버** — 새 특성화 테스트 불필요:
- `tests/benchmark/test_config.py` — `BenchmarkConfig`/`DEFAULT_BASELINES` 파싱·검증.
- `tests/benchmark/test_runner.py` — `BenchmarkConfig` 사용 경로.
- `tests/test_early_session.py` — `EarlySessionConfig`.
- `tests/test_f56_bugfixes.py` — `EarlySessionConfig` 사용 경로.

**베이스라인 실행(이 worktree)**: `pytest tests/benchmark/test_config.py tests/benchmark/test_runner.py
tests/test_early_session.py -q` → **42 passed** (green). Stage 4 내내 이 집합 + `test_f56_bugfixes.py`를
green 유지; red = 동작 변경 신호 → 정지.

## 결론

순수 모듈 개명(2건) + import 10곳(main.py:512 포함) + doc 1곳 갱신. 클래스명·YAML 키·동작 전부 불변. **all-T1, T3 게이트 없음.**
