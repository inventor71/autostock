# R12 Post-Merge Guide — brokers 네이밍 정합

머지 후 prod에서 바뀌는 것과 확인 절차. (코드 동작은 보존 — 유일한 외부 변경은 provider 값 클린브레이크.)

## 무엇이 바뀌나
- 모듈: `broker_api_broker.py`→`account_farm_broker.py`, `simulated.py`→`simulated_broker.py`,
  `kis_{broker,pricing,rest}.py`→`kis/{broker,pricing,rest}.py`. 클래스 `BrokerApiBroker`→`AccountFarmBroker`.
- **provider 값 클린브레이크**: `broker.provider: broker_api` → **`account_farm`** (별칭 없음).
- **T3-2**: 미지 provider는 이제 부팅 시 `ValueError`로 **명시 실패** (이전: 조용히 alpaca 폴백).

## 머지 전/후 체크리스트
1. **설정 확인**: `grep -n "provider" config/settings.yaml` — 현재 운영값은 `alpaca`(영향 없음).
   어떤 배포/백업 yaml이든 `provider: broker_api`가 있으면 → `account_farm`으로 1줄 수정.
   (수정 안 하면 데몬 부팅 시 `ValueError: Unknown broker.provider 'broker_api'` — 조용한 오동작 아님.)
2. **데몬 재시작**: 모듈 경로가 바뀌었으므로 구버전 데몬은 F43 버전-스큐 자가치유로 재시작되거나,
   `autostock` 런처 재실행으로 새 코드 로드.
3. **스모크**: 데몬 기동 로그에 broker 초기화 라인(`AccountFarmBroker initialized` 또는 Alpaca/KIS) 확인.
   `scripts/health.py` config_env 차원 OK 확인(provider 검사는 `account_farm` 키로 갱신됨).

## 롤백
revert 커밋 1개로 원복(파일 rename + 참조 갱신이 단일 커밋). 설정을 `broker_api`로 되돌릴 필요는
롤백 시에만 발생.

## 범위 밖 (불변)
- env 키 `BROKER_API_KEY/SECRET`, `BROKER_ACCOUNT_ID` 및 settings 필드 `broker_api_key/...` —
  Alpaca "Broker API" 제품 자격증명 명칭이라 유지.
- BaseBroker 계약·R3 `_alpaca_shaped` 훅·KIS REST 1-token/min 공유 캡.
