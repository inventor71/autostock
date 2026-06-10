# Tier Ledger — R12 execution/brokers 네이밍 정합

범위: broker_api_broker→account_farm_broker + simulated→simulated_broker + kis_*→kis/ (구조점검 #6)
작성일: 2026-06-11

## T1 — 동작 보존 (자율 진행)
| # | 변경 항목 | 보존되는 동작 | 보존 검증 방식 | 근거 |
|---|-----------|---------------|----------------|------|
| 1 | `broker_api_broker.py` → `account_farm_broker.py` (`git mv`) + 클래스 `BrokerApiBroker`→`AccountFarmBroker` | BaseBroker 계약·AlpacaShapedBroker 훅 동작 동일 | `test_broker_api_broker.py`(개명→`test_account_farm_broker.py`) PBT 포함 green | 식별자 개명만; R3 베이스 불변 |
| 2 | import/참조 갱신: `main.py:48-49`, `benchmark/runner.py:78,103,118(_mask)`, tests 3파일, **문자열 monkeypatch `test:432`** | import 동일 객체 | 위 테스트 green | 경로/이름만 |
| 3 | 주석/문서 갱신: `_alpaca_shaped.py`(8), `alpaca_broker.py:38`, `README.md:130` | (주석) | n/a | 정합성 |
| 4 | `simulated.py` → `simulated_broker.py` + import 16곳 | `SimulatedBroker` 동작 동일 | 기존 테스트 다수(16곳 중 13 tests) green | 모듈명만 |
| 5 | `kis_{broker,pricing,rest}.py` → `kis/{broker,pricing,rest}.py` (+빈 `kis/__init__.py`) + import 9곳(내부 2 + 외부 7: main/kr_provider/factory/kis_provider/tests 3) | KIS 브로커·pricing·REST 공유 캡 동작 동일 | `test_kis_*` 3파일 green | 위치만; brokers/__init__ 재export 없음 확인 |
| 6 | 테스트 파일명 `test_broker_api_broker.py`→`test_account_farm_broker.py` | 테스트 내용 동일 | 수집 수 동일 | 개명 모듈 native 미러 |

## T2 — 안전한 확장
없음.

## T3 — 의도 변경 (승인 필요/사전 승인)
| # | 변경 내용 | 이유 | 영향 범위 | 사용자 결정 |
|---|-----------|------|-----------|-------------|
| 1 | provider 리터럴 `"broker_api"` → `"account_farm"` (`main.py:37,47`, `config_env.py:72-73`, `config/config.py:27-29` 주석, `settings.yaml:15` 주석, **`README.md:134,137`, `.env.example:6`** ← critic 추가) | 모듈/클래스와 이름 정합; 별칭 유지 = 영구 clutter | **운영 yaml은 `provider: alpaca`** → 실질 영향 주석/문서 수준. post-merge-guide에 마이그레이션 1줄 | **승인** — 2026-06-08 클린브레이크 정책 + 2026-06-11 이름 `account_farm` 확정 |
| 2 | `create_broker`에 **미지 provider 명시 raise** 추가 (현행: 조용히 alpaca 폴백, main.py:55-61) | 클린브레이크가 "fails loud"이려면 필수 — 없으면 구 `broker_api` 설정이 **조용히 alpaca 계정으로 트레이딩**(critic HIGH) | 유효 provider(`alpaca`/`account_farm`)는 동작 불변; **잘못된 값만** 폴백→ValueError로 변경 | **게이트 승인 대기** (이번 설계 승인에 포함) |

## 정지 지점
- [x] T3-1 결정 완료 (클린브레이크 사전승인 + UAQ 이름 확정)
- [ ] T3-2 (create_broker 미지 provider raise) — 설계 게이트에서 승인 대기
- [x] 모든 T1 항목이 기존 broker 테스트(133)로 보호됨; provider 디스패치는 create_broker 스모크로 보강
