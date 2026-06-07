# F70 / benchmark — NFR Requirements + Design (경량)

## NFR-1 — 프로덕션 무영향 (최우선)
- **요구**: 라이브 LLM 계정/주문 경로를 절대 건드리지 않는다.
- **설계**:
  - baseline은 `config/benchmark.yaml`의 `accounts` 맵에 명시된 **sandbox 계정**에만 주문.
  - 빌드 시 baseline 계정 ID ∈ {라이브 `broker_account_id`} 검사 → 충돌 시 해당 baseline 제외(BR-3).
  - 마스터 토글 `enabled` **기본 false**. off면 `run_agent` 흐름에서 러너 생성·스레드·주문 전무.
  - 러너 스레드 예외는 baseline 단위 격리(BR-4) → 데몬/agent 루프에 전파 불가.

## NFR-2 — 운영 부담 한계
- **요구**: 5개 baseline의 추가 API 호출이 rate-limit/데몬 지연을 유발하지 않을 것.
- **설계**:
  - `data_provider` **라이브와 공유** → 시장데이터 중복 fetch 0 (가장 큰 호출원 제거).
  - cadence 기본 **EOD 1회**(`interval_minutes: "eod"`). baseline tick은 순차 실행(동시 5계정
    버스트 회피); 계정당 주문은 보통 소수(일 1회 신호).
  - 러너는 별도 스레드 → agent 턴 블로킹 없음.

## NFR-3 — 저장 비용
- **요구**: equity 스냅샷 무한 증가 방지.
- **설계**: append-only JSONL. `retention_days`(기본 365) 초과 레코드는 `metrics` CLI 또는 러너
  기동 시 1회 컴팩션(원천은 충분히 길게 보존 — NFR-4와 균형). 일 1회×6계열이라 용량 미미.

## NFR-4 — 재현 가능 분석
- **요구**: 지표 공식이 바뀌어도 과거 재산출 가능.
- **설계**: 원천 equity 시계열(`equity/<strategy>.jsonl`)과 파생 지표(`metrics/<ts>.jsonl`)를
  물리 분리. `compute_metrics` 순수함수(BR-6) → 저장된 원천만으로 `python -m src.benchmark.metrics`
  재실행. 지표 파일은 스냅샷(덮어쓰기 아님, 시점별 append).

## NFR-5 — 보안 (Security Baseline, 적용 범위 한정)
- 계정 자격증명/`account_id`는 settings/env에서만 로드, 코드/로그/저장 파일에 평문 미포함.
- 스냅샷의 `account_masked`는 `BrokerApiBroker._mask` 패턴 준수(끝 일부만 노출).
- `BrokerApiBroker` 생성자의 fail-closed(자격증명 누락 시 BrokerError) 그대로 활용.
- N/A: 인증/인가 흐름, 외부 노출 엔드포인트(본 트랙은 내부·로컬 파일).

## NFR 검증 매핑 (Build & Test에서)
| NFR | 검증 |
|-----|------|
| 1 | 단위테스트: 계정충돌 baseline 제외 / toggle off 시 러너 no-op / tick 예외 격리 |
| 2 | 설계 리뷰 + data_provider 공유 단위테스트(중복 fetch 없음 mock 호출수) |
| 3 | retention 컴팩션 단위테스트 |
| 4 | metrics 순수성: 동일 입력→동일 출력 (PBT 라운드트립) + CLI 재산출 스모크 |
| 5 | 스냅샷에 평문 계정/시크릿 미포함 단위테스트(account_masked만) |
