# R9 Stage 3 — Redesign (목표 구조 + 마이그레이션)

범위: config↔settings 용어 통일 (all-T1) · 작성일: 2026-06-09

## 목표 구조

패키지 로컬 설정 모듈을 **`settings.py`로 통일**, 클래스는 `*Config`로 유지(확립된 관례):

| 패키지 | before | after | 클래스(불변) |
|--------|--------|-------|--------------|
| benchmark | `config.py` | `settings.py` | `BenchmarkConfig`, `DEFAULT_BASELINES` |
| early_session | `config.py` | `settings.py` | `EarlySessionConfig` |
| signals/surge/intraday | `settings.py` (이미) | (변경 없음) | `*Config` (이미) |

전역 설정 repo-root `config/config.py::get_settings()`는 **유지**(역할: 전역=config / 로컬=settings).

## 명명 규칙 (확정)
- **로컬 패키지 설정 모듈 = `settings.py`**, 그 안의 설정 클래스 = `<Domain>Config`.
- 클래스명은 손대지 않는다(이미 규칙 준수, 개명하면 오히려 import 9곳 외 추가 변경 = 불필요한 위험).
- **결정(Stage 1 거리)**: `tests/benchmark/test_config.py` → `tests/benchmark/test_settings.py` 동반 개명.
  근거: 방금 개명한 모듈을 native하게 미러; 트랙ID 기반 이름이 아니라 R13(테스트 명명 정비) 범위와 겹치지 않음.
  (`tests/test_early_session.py`는 모듈명과 무관한 행동 기반 이름이라 그대로 둔다.)

## 동치성 논증 (왜 T1인가)
- Python 모듈 = 파일. `git mv config.py settings.py`는 **정의(클래스/상수/함수) 바이트 동일**, 위치만 이동.
- import는 `from src.X.config import Y` → `from src.X.settings import Y`로 심볼 `Y`는 동일 객체를 가리킨다.
- YAML 로딩은 `getattr(settings, "benchmark")` / `early_session:` 블록명에 의존 → **모듈 경로와 무관**, 불변.
- 동적 import/`-m`/문자열 모듈경로 참조 0건(Stage 1 sweep) → 숨은 호출부 없음.
- ∴ 외부 관측 동작 동일 → 순수 T1. red 발생 시 = 누락된 import → 고치면 green(동작 변경 아님).

## 마이그레이션 순서 (작은 단위, 단계마다 green 확인)
1. `git mv src/benchmark/config.py src/benchmark/settings.py`; `git mv src/early_session/config.py src/early_session/settings.py`.
2. `git mv tests/benchmark/test_config.py tests/benchmark/test_settings.py`.
3. import **10곳**(`main.py:512` 포함) + doc 자기참조 1곳 일괄 갱신(`…config`→`…settings`).
4. `rg 'benchmark\.config|early_session\.config' --glob '!aidlc-docs/**'` 재확인 = 0 (잔여 없음).
   ※ 스코프 필수 — repo-wide면 R9 자신/타 트랙 설계문서에 매칭돼 거짓 실패(critic LOW).
5. 영향 테스트 green: `pytest tests/benchmark tests/test_early_session.py tests/test_f56_bugfixes.py -q`.
6. **`main.py:512` 경로는 테스트 미커버** → `python -c "from main import _maybe_start_benchmark"` import 스모크
   + `python -c "import main"` 로 모듈 로드 확인(벤치마크 비활성 기본이라 부팅엔 영향 없지만 import 깨짐 검출).
7. 전체 스위트 green + `py_compile main.py src/benchmark/settings.py src/early_session/settings.py` 클린 (Build & Test).

## 영향 없음 확인
- 클래스명/필드/기본값/YAML 키/CLI/출력 전부 불변. post-merge-guide 불필요(외부 표면 변화 0).
