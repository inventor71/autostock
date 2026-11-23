# Track F101 — 기존 toss-stock 인증으로 Autostock 연결

- **Status**: merged → main 24b32f7 (2026-11-23, local)
- **Branch**: feat/F101
- **Worktree**: — (merged; temporary worktree removed)
- **Base commit**: e082768
- **Start Date**: 2026-11-23

## 범위와 결정

사용자가 기존 toss-stock 인증으로 연결하도록 요청했다. 키를 복사하거나 새 토큰을
발급하지 않는다. toss-stock의 토큰 파일을 실행 시점에 읽고, Autostock에는 파일 경로와
검증된 계좌 선택만 0600으로 저장한다. 토큰 갱신 주체는 기존 toss-stock으로 유지한다.
공유 토큰 연결은 읽기 전용으로 고정한다. 만료·폐기·잘못된 권한은 명확히 실패한다.

기존 toss-stock 코드/프로세스, Autostock 기본 broker/실행 데몬은 변경하지 않는다.
사용자의 구현·연결 요청과 이전 자율 진행 승인을 적용하여 별도 단계 승인 없이 진행한다.

## Extension Configuration

- Security Baseline: F100과 동일, 별도 확장 opt-in 없음. 비밀값 비노출·읽기 전용 경계 검증.
- Property-Based Testing: F100과 동일, 별도 확장 opt-in 없음. 모의 HTTP와 실패 경로 검증.

## 구현 및 검증 계획

- [x] 기존 toss-stock의 인증/토큰 갱신·계좌 캐시 경로 확인
- [x] Credentials에 공유 토큰 참조 모드 추가 (키와 동시 사용 금지)
- [x] Client에 읽기 전용 토큰 소비, 회전 감지, 만료/오류 처리 추가
- [x] setup --from-toss-stock으로 검증 후 계좌 연결 저장
- [x] 토큰 경쟁·인증 갱신 금지·권한·계좌 선택·기존 연결 보존 테스트
- [x] 전체 Python 회귀 테스트, 실제 읽기 전용 계좌·시세 조회
- [x] 사용 안내 및 AI-DLC 기록 후 로컬 main에 반영

## Merge Risk Notes

- F100의 Toss credentials/client/setup, docs/TOSS.md 변경.
- 기존 ID/secret 인증 모드는 유지하며 공유 토큰 모드만 추가한다.
- F98/F99 및 toss-stock의 진행 중 변경은 수정하지 않는다.
- 외부 모니터링이 중지되어 토큰이 만료되면 공유 연결은 조회를 중단한다.

## 검증 결과

- Toss 테스트 99개 통과 (신규 17개), 전체 Python 1,770개 통과 (기존 경고 30개).
- 변경된 Toss 모듈/테스트 Ruff 및 git diff --check 통과.
- 실제 공유 토큰으로 setup 연결 완료. 계좌·보유종목·USD 구매력 검증 성공.
- Autostock broker와 data provider로 US 자산 조회, AAPL 시세, 완성 일봉 3개 조회 성공.
- 새 토큰 발급·주문·비밀값 복사 없음. 계좌·잔액 등 개인 금융 데이터는 기록하지 않음.
