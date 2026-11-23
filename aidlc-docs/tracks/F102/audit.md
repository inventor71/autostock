# F102 Audit

## 2026-11-23 — User request

> 일단은 요율 적용이 만료되면 자동으로 다시 확인하도록 해서 앞으로 문제 없도록 만들어줘. 연간 양도소득세는 따로 처리한다고 생각하자.
> 이번에 구현한 toss-autostock을 평가하고 싶은데 dry모드로 몇일동안 켜두고, 만약 agent 대로 했다면 어땟을지를 감시하는 모드를 만들고 싶은데, 그 경우에는 아무래도 어떤 호가로 채결이 되고, 그것에 대한 가상 시나리오 및 계좌를 관리하는 것이 필요할 것으로 보이는데 할 수 있나? 이 dry 모드는 alpaca 쪽 계좌에 toss 내 계좌의 현 상황을 mirroring하는 계좌를 만들어두고, 그를 통해서 몇일 동안 가상으로 돌리면서 evaluate해볼 수 있지 않을까 싶네 (물론 그때 토스 기준 비용반영이 현실적으로 되었으면 좋겠어) 가능할까? 아니면 이 목적을 달성하기 위한 다른 더 좋은 해법이 있을까?

## 2026-11-23 — Assessment

Toss API 1.2.28의 commissions 종료일은 KST 날짜. 계좌 US 요율 0.001,
종료일 2026-11-24를 직전 read-only 조사에서 확인했다. Alpaca 공식 paper 문서는
latency slippage / regulatory fees / liquidity constraints 미반영을 명시한다.
Toss GET 시세 + 독립 로컬 장부가 해당 비교 목적에 더 적합하다.
worktree F102 생성. 기존 프로세스/계좌/토큰은 변경하지 않는다.

## 2026-11-23T10:05:29Z — Construction, review and verification

계좌별 요율 만료/6시간 재조회, 독립 가상 USD 장부, bid/ask와 잔량 기반 지연 체결,
부분 체결·보호 주문·현금 예약, 동일 초기 buy-and-hold 비교, durable bounded runner 구현.
모델 프롬프트에는 비용과 가상 계좌 문맥만 짧게 추가했다. 연간 양도소득세 제외.
규제비용 추정은 Q4 2026에 한정하고 이후 검토 전 체결을 보류한다.

리뷰에서 KIS legacy 설정 호환, 부분 체결의 요율 변경, 실패 모델의 부분 journal 복구,
HTTP 요청 중 요율 만료/정규장 종료 경계를 보완했다. 최종 1806 tests passed, 30 기존
경고, 새 모듈 Ruff 및 diff check 통과. 실제 공유 토큰으로 init/run --once/report,
강제 요율 재조회/AAPL orderbook 파싱 검증 성공. GET 외 HTTP 차단 hook 검증 2 GET,
주문·토큰 발급·모델 호출 0회. 원격 push, 기존 데몬 재시작, 장기 agent 실행 없음.
단기 가상 성과/수익 향상을 입증했다는 주장은 하지 않는다.
