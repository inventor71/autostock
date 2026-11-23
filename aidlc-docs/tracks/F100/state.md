# Track F100 — 토스증권 OpenAPI 연동과 안전한 계좌 연결

- **Status**: merge-awaiting
- **Branch**: feat/F100
- **Worktree**: .claude/worktrees/F100
- **Base commit**: 749d641
- **Start Date**: 2026-11-23

## 범위와 결정

기존 BaseBroker / BaseDataProvider 경계를 유지한다. 공식 REST 스펙 v1.2.28을 기준으로
인증, 계좌/보유종목/주문 조회, 단순 주문과 시세 공급자를 구현한다. 인증 정보는 저장소
밖의 사용자 전용 파일에 저장하고, 연결 명령은 읽기 전용 검증만 수행한다.
Alpaca 기본 설정과 실행 중인 데몬은 변경하지 않는다. 토스의 limit-only OCO를 기존
stop-market bracket으로 가장하지 않는다. 지원되지 않는 주문은 제출 전에 거부한다.

사용자의 구현 및 자율 진행 승인을 적용하여 단계별 재승인 없이 로컬 구현/검증을 진행한다.
실거래 실행은 요청 범위에 포함되지 않는다. CodeKB는 참고만 하고 실제 연결 지점을 재확인한다.

## Extension Configuration

- Security Baseline: 별도 확장 opt-in 없음. 요청된 비밀정보 보호/읽기 전용 기본값을 직접 검증.
- Property-Based Testing: 별도 확장 opt-in 없음. API 계약과 실패 경로 중심의 결정적 테스트.

## Stage Progress

- [x] Workspace Detection / 기존 인터페이스 분석
- [x] Requirements / Workflow Planning — 아래 계획으로 통합
- [x] Design — 계좌 연결, 공유 토큰, 주문 기능 차이, 통화 및 캔들 시간 규칙
- [x] 인증/비밀정보 저장 및 연결 CLI
- [x] REST broker / market data / factory / config 연결
- [x] 계약 및 회귀 테스트 — 전체 1,753 passed, 신규 Toss 82개
- [x] 사용 안내와 검증 기록 — docs/TOSS.md / construction/verification.md

## 구현 계획

1. 숨김 입력, 0700 디렉터리/0600 파일, 원자적 저장. API 오류에 비밀정보를 포함하지 않는다.
2. 단일 유효 토큰을 프로세스 간 공유하고 잠금으로 재발급을 직렬화한다.
3. 읽기 전용 기본값과 명시적 실거래 설정을 분리한다. paper=true를 실거래로 해석하지 않는다.
4. 제출 승인과 실제 체결을 구분하고, 불명확한 제출 결과를 자동 재전송하지 않는다.
5. 시세 페이지네이션/1분봉 종료시각/미완성 봉/통화 분리를 검증한다.
6. 네트워크 없는 회귀 테스트. 실제 계좌 검증은 사용자가 로컬에서 키를 입력한 뒤 수행한다.

## Merge Risk Notes

- 공유 파일: config/config.py, config/settings.yaml, main.py, broker factory, health checker.
- 기존 공개 시그니처 유지. 신규 provider는 명시적으로 선택해야 한다.
- F98/F99 워크트리는 건드리지 않는다.
- health probe는 생성한 Toss HTTP client를 닫는다. F99의 일반 FD 누수 변경은 별도 범위.

## 구현 결과와 제한

- US/USD broker + KR/US data class. 기본 composition은 US, 계좌 연결 후에도 읽기 전용.
- 문서화된 모의 endpoint 없음: Toss provider에 paper=true를 적용하면 즉시 실패.
- MARKET/LIMIT DAY 주문, 실제 체결량, 취소 확인, US 가격 정정, 계좌 분리 지원.
- bracket/stop/trailing/short는 제출 전 거부. 자동 agent 시작도 차단하여 보호 없는 진입 방지.
- 조건주문이 존재하면 불완전한 일반 주문 목록을 반환하지 않고 Toss에서 관리하도록 안내.
- 사용 가능 USD 현금 + 보유종목 평가액은 NAV가 아니므로 수익률 원장에 기록하지 않는다.
- 웹소켓 fill feed / 실제 매매 / 실제 계좌 검증은 수행하지 않았다. 마지막 검증은 사용자가
  자신의 터미널에서 숨김 입력으로 계좌를 연결한 뒤 실행해야 한다.
- API 계약 테스트는 안정성 검증이며 수익률 개선의 증거가 아니다.
