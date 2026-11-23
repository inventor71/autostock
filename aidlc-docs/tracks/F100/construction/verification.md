# F100 검증 기록

2026-11-23, feat/F100 작업 트리에서 main의 Python 3.12 venv로 실행.

## 결과

- `python -m pytest tests -q`: **1,753 passed**, 30 기존 deprecation warnings, 33.43초.
- 신규 Toss 테스트: **82개**. 공식 OpenAPI 1.2.28 공개 예제와 httpx MockTransport 사용.
- 신규 Toss 코드/테스트 Ruff: 통과.
- `git diff --check`: 통과.
- `python -m src.execution.brokers.toss.setup --help`: 통과.
- 기존 파일 전체 Ruff에는 기존 lint 부채가 남아 있다. 관련 없는 자동 수정은 하지 않았다.

## 검증한 실패 경로

- 읽기 전용 설정이 HTTP/토큰 발급 전 쓰기를 거부한다.
- 클라이언트/프로세스 간 토큰 공유, 인증 만료 및 제한된 GET 재시도.
- HTTP 오류/리다이렉트에 비밀정보가 출력되거나 다른 호스트로 전달되지 않는다.
- 제한된 파일 권한, symlink 거부, TTY 없는 비밀정보 입력 거부, 실패 시 기존 키 보존.
- 불명확한 주문 제출은 재시작 후에도 재전송하지 않는다. 서버의 10분 멱등키 유효기간을
  넘겨도 이미 승인된 동일 주문을 새로 만들지 않는다.
- 제출 승인을 체결로 기록하지 않는다. 부분체결 수량/평균가/비용만 사용한다.
- 취소 승인만으로 수량을 해제하지 않는다. 원주문의 취소 상태를 확인한다.
- 수정 후 새 주문 ID를 사용하고, 읽기 실패 시에도 승인된 ID를 잃지 않는다.
- unsupported bracket 교체가 기존 보호 주문을 먼저 취소하지 않는다.
- Toss name/provider 불일치가 Alpaca 계좌로 조용히 연결되지 않는다.
- 통화 분리, 데이터 페이지 경계 중복, 1분봉 종료→시작 시각 변환, 미완성 봉 제외.
- 현금 매수 가능액을 총계좌 NAV로 간주한 수익률 기록 금지.
- 신규 factory 연결이 기존 KIS 설정 객체와 OpenAI health 검증을 유지한다.

## 실제 계좌 연결

키를 전달받거나 실제 계좌를 호출하지 않았다. 사용자는 저장소 루트에서 다음을 실행한다:

```bash
venv/bin/python -m src.execution.brokers.toss.setup
venv/bin/python -m src.execution.brokers.toss.setup --check
```

연결은 읽기 전용이다. 기존 daemon 재시작, 브로커 전환, 실거래 활성화는 하지 않았다.
