# R12 Stage 3 — Redesign (목표 구조 + 마이그레이션)

범위: brokers 네이밍 정합 (T1 + 승인된 클린브레이크 1건) · 작성일: 2026-06-11

## 목표 구조

```
src/execution/brokers/
  _alpaca_shaped.py        # 불변 (R3 베이스)
  alpaca_broker.py         # 불변 (주석 1곳만 갱신)
  account_farm_broker.py   # ← broker_api_broker.py (클래스 AccountFarmBroker)
  simulated_broker.py      # ← simulated.py (클래스 SimulatedBroker 불변)
  session_timeout.py       # 불변
  kis/
    __init__.py            # 빈 파일 (재export 없음 — 호출부 직접 갱신)
    broker.py              # ← kis_broker.py (KisBroker/KisPaperBroker/_OcoStore 불변)
    pricing.py             # ← kis_pricing.py
    rest.py                # ← kis_rest.py (KisRestClient — data provider와 공유)
```

명명 규칙: 브로커 모듈 = `*_broker.py`(디렉터리가 brokers/지만 alpaca·kis와의 가독 일관 유지),
멀티파일 브로커는 서브패키지(`kis/`). provider 값 = 도메인 의미(`alpaca`/`kis`/`account_farm`).

## 동치성 논증
- `git mv` = 정의 바이트 동일. 클래스 개명(`BrokerApiBroker`→`AccountFarmBroker`)은 내부 식별자 —
  공개 계약은 BaseBroker 인터페이스이며 클래스명에 의존하는 외부 직렬화/문자열 디스패치 없음
  (provider 디스패치는 리터럴 비교, 클래스명 아님).
- `kis/` 이동: brokers/__init__·execution/__init__ 둘 다 빈 파일(재export 없음) → 호출부 7곳 직접 갱신으로 충분.
- 문자열 monkeypatch(`test:432`)는 전수검사에 포착됨 — 함께 갱신.
- provider `"account_farm"`: 승인된 클린브레이크. 운영 yaml=alpaca라 무영향.
  ⚠️ **정정(critic)**: 현행 `create_broker`는 미지 provider를 **조용히 alpaca로 폴백**(main.py:55-61) —
  "명시 실패" 주장은 틀렸었음. 따라서 **T3-2: 미지 provider `raise ValueError` 추가**(유효 값 동작 불변,
  잘못된 값만 폴백→명시 실패). 이것 없으면 구 `broker_api` 설정이 조용히 alpaca 계정으로 트레이딩.

## 마이그레이션 순서 (단계마다 green)
1. `git mv broker_api_broker.py account_farm_broker.py`; 내부 클래스/로그문자열 `BrokerApiBroker`→`AccountFarmBroker`.
2. `git mv simulated.py simulated_broker.py`.
3. `mkdir kis` + `git mv kis_broker.py kis/broker.py`, `kis_pricing.py kis/pricing.py`, `kis_rest.py kis/rest.py`
   + 빈 `kis/__init__.py`; `kis/broker.py` 내부 import 2곳(`…kis_pricing`→`…kis.pricing`, `…kis_rest`→`…kis.rest`).
4. 외부 참조 일괄 갱신:
   - account_farm: `main.py:48-49`, `benchmark/runner.py:78,103,118`, `tests/{test_broker_api_broker,benchmark/test_runner,test_short_etb_gate}.py`(문자열 monkeypatch 포함)
   - simulated: 16곳 = `backtest/engine.py:14` + 테스트 15파일 (critic 정정: main.py 아님; `test_f56:108` 함수-로컬 주의)
   - kis: `main.py:41`, `universe/{kr_provider:12,factory:33}.py`, `data/providers/kis_provider.py:18`, `tests/test_kis_{broker,integration,pricing}.py`
   - 주석/문서: `_alpaca_shaped.py`(8), `alpaca_broker.py:38`, `README.md:130`
5. provider 클린브레이크: `main.py:37,47` + `config_env.py:72-73` + `config/config.py` 주석 + `settings.yaml:15` 주석
   + **`README.md:134,137`(전환 가이드) + `.env.example:6`** → `"account_farm"`.
   **+ T3-2(승인 시)**: `create_broker`의 alpaca 폴백 앞에 `if provider not in ("alpaca",): raise ValueError(...)`
   형태의 미지-provider 명시 실패 추가(유효 값 동작 불변).
6. `git mv tests/test_broker_api_broker.py tests/test_account_farm_broker.py`.
7. 잔여 0 확인: `rg 'broker_api_broker|BrokerApiBroker|brokers\.simulated\b|brokers\.kis_(broker|pricing|rest)|"broker_api"' --glob '!aidlc-docs/**'`
   (단, `broker_api_key/secret/account_id` 필드·`BROKER_API_*` env는 제품 명칭 — 잔여 아님, 패턴에서 제외).
8. 검증: broker 테스트 일괄 green → **create_broker 스모크** — 브로커 생성자를 monkeypatch한 스크립트로
   3분기(alpaca/kis/account_farm) **디스패치만** 검증(실 네트워크/KIS 토큰 소비 없음; `factory.py:33`
   함수-로컬 import는 KIS 분기 호출로 실행됨) + 미지 provider raise 확인 → 전체 스위트 + py_compile.
9. **post-merge-guide** 작성: provider 값 `broker_api`→`account_farm` 마이그레이션 1줄 + 데몬 재시작.

## 영향 없음 확인
BaseBroker 계약·R3 훅·KIS 1-token/min 공유 캡·env 키 전부 불변.
