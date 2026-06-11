# R12 Stage 1 — Baseline + 특성화 (execution/brokers 네이밍 정합)

범위: `broker_api_broker` 개명 + `simulated`→`simulated_broker` + `kis_*`→`brokers/kis/` (구조점검 #6)
작성일: 2026-06-11 · Base: `0106a8b` · Branch: `refactor/R12` · Worktree: `.claude/worktrees/R12`

## 현재 구조

```
src/execution/brokers/
  _alpaca_shaped.py      # R3 공유 베이스 (유지)
  alpaca_broker.py       # 유지
  broker_api_broker.py   # ← "broker_api + broker" 이름만으론 불명 (sandbox account-farm 어댑터, F16)
  simulated.py           # ← 유일하게 _broker 접미사 없음
  kis_broker.py          # ← kis 3형제 → kis/ 서브패키지 후보
  kis_pricing.py
  kis_rest.py
  session_timeout.py     # 유지 (broker 아님 — 헬퍼)
```

## 변경 영향 인벤토리 (전수검사 — repo-wide `rg`, `!aidlc-docs`)

**1) `broker_api_broker.py` (모듈+클래스 개명 — 이름은 Stage 3 사용자 결정):**
- 모듈 import: `main.py:48`, `src/benchmark/runner.py:78`, `tests/test_broker_api_broker.py:12,84,460,479`,
  `tests/benchmark/test_runner.py:53`, `tests/test_short_etb_gate.py:158`
- **문자열 monkeypatch**: `tests/test_broker_api_broker.py:432` — `"src.execution.brokers.broker_api_broker.record_trades"`
- 클래스 `BrokerApiBroker` 언급(주석/문서): `_alpaca_shaped.py`(8곳, docstring), `alpaca_broker.py:38`, `README.md:130`
- 테스트 파일명 `tests/test_broker_api_broker.py` → 새 이름 동반 개명
- **provider 리터럴 `"broker_api"` (클린브레이크 — 등록 시 결정 2026-06-08)**:
  `main.py:37(docstring),47(디스패치)`, `src/monitoring/health/dimensions/config_env.py:72,73`,
  `config/config.py:27-29(주석)`, `config/settings.yaml:15(주석)`,
  **`README.md:134,137`(전환 가이드 YAML 스니펫), `.env.example:6`** ← critic이 잡은 누락 2곳.
  **운영 settings.yaml의 실제 provider는 `alpaca`** → 라이브 설정 마이그레이션 부담 없음(주석만).
  ⚠️ **`create_broker`는 미지 provider를 조용히 alpaca로 폴백**(main.py:55-61, raise 없음) — 클린브레이크
  후 구 `broker_api` 설정이 **조용히 alpaca 계정으로 트레이딩**하게 됨. "fails loud"를 위해 미지 provider
  명시 raise 추가 필요(T3-2, 게이트에서 승인).

**2) `simulated.py` → `simulated_broker.py`:** import 16곳 = `src/backtest/engine.py:14` + **테스트 15파일**
   (critic 정정: `main.py`는 simulated를 import하지 **않음**; `test_f56_bugfixes.py:108`은 함수-로컬 import 주의).
   클래스 `SimulatedBroker` 이미 정상 — 모듈명만.

**1b) 문자열/setattr monkeypatch (전수 — 2곳):** `tests/test_broker_api_broker.py:432`
   (`"src.execution.brokers.broker_api_broker.record_trades"`) + **`tests/benchmark/test_runner.py:53,57`**
   (`import … as bap` + `setattr(bap, "BrokerApiBroker", …)`). 추가로 `tests/test_short_etb_gate.py:158-170`이
   `BrokerApiBroker._position_side` 정적 접근 — 클래스 개명과 함께 갱신.

**3) `kis_{broker,pricing,rest}.py` → `brokers/kis/{broker,pricing,rest}.py`:**
- `kis_rest`(4): `src/universe/kr_provider.py:12`, `src/universe/factory.py:33`, `kis_broker.py:34`,
  `src/data/providers/kis_provider.py:18` ← **data-provider와 REST 클라이언트 공유**(등록 시 critic 지적)
- `kis_pricing`(2): `kis_broker.py:33`, `tests/test_kis_pricing.py:9`
- `kis_broker`(3): `main.py:41`, `tests/test_kis_broker.py:10`, `tests/test_kis_integration.py:10`
- 테스트 파일명(`test_kis_*.py`)은 행동 기반이라 유지.

**범위 밖(명시):** `BROKER_API_KEY/SECRET/ACCOUNT_ID` env 키와 `settings.broker_api_key` 필드 — Alpaca
"Broker API" **제품** 자격증명 명칭으로 정당. env 키 개명은 훨씬 큰 외부 브레이크라 R12에서 안 건드림.

## 보존해야 할 관측 가능 동작 (외부 계약)
- 세 브로커 클래스의 공개 BaseBroker 계약(주문/포지션/fill 동작) byte-for-byte.
- `_alpaca_shaped.py` 베이스 훅 계약(R3) 불변.
- KIS REST 1-token/min 공유 캡(`factory.py:31-33` 주석 경로) 불변.
- **변경**: 모듈 경로/클래스명/provider 리터럴(클린브레이크 승인분)만.

## 특성화 테스트 (안전망)
- `test_broker_api_broker.py`(mapper PBT 포함, R3) + `test_alpaca_broker.py`(36, R3) + `test_kis_broker.py`
  + `test_kis_pricing.py` + `test_execution.py` → **베이스라인 133 passed** (이 worktree).
- provider 디스패치(`main.py:47`)는 테스트 미커버 → import smoke + `create_broker` 분기 스모크로 보강.

## 동시 트랙 주의
- R9(merge-awaiting): `main.py:512`/`runner.py:10` — R12와 **다른 라인**.
- R11(merge-awaiting): `main.py:92-99`/`runner.py:20-21` — 다른 라인.
- R12: `main.py:37-57,528-529 인접`/`runner.py:78,103,118`. 세 트랙 모두 main.py+runner.py를 만지므로
  **머지 순서대로 rebase-verify 필수**(자동 결합 예상, 충돌 시 라인 분리 명확).

## 결론
T1(모듈/클래스 개명 + import 전수) + **승인된 클린브레이크 1건**(provider 리터럴 — 운영 yaml은 alpaca라
실질 영향 주석 수준, post-merge-guide 필요). 새 이름 결정(Stage 3 게이트)만 사용자 입력 필요.
