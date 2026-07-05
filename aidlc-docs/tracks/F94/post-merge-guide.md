# F94 Post-Merge Guide — 콘솔 계좌-read provider 정합성

> 대상: 운영 중인 Docker prod 3개 인스턴스. 코드는 머지로 /app(main 체크아웃)에 반영되지만,
> **이미 떠 있는 콘솔(opencode)은 옛 mcp-server 코드를 들고** 있으므로 재접속이 필요하다.
> 데몬 재시작은 불필요(콘솔 read는 데몬이 이미 발행하는 snapshot.json만 읽는다).

## prod에서 무엇이 바뀌나
- 콘솔 채팅의 계좌-read 툴(`get_account_info`/`get_all_positions`/`get_open_position`/
  `get_orders`/`get_portfolio_history`)이 **provider-aware**가 됨.
  - account_farm 인스턴스 → 데몬 snapshot.json(자기 sub-account 진실)에서 읽음.
  - alpaca 인스턴스 → 기존 Alpaca 직결(불변).
- 시장데이터 툴(시세/바/캘린더 등)·mutating 툴(close/cancel)은 불변.

## 절차 (인스턴스마다)
1. F94가 main에 머지됨(확인).
2. 열려 있던 콘솔 종료(Ctrl-C) 후 재접속:
   ```
   scripts/prod-run.sh attach aggressive   # balanced / conservative 도
   ```
   (재접속이 새 mcp-server를 띄워 새 코드를 로드. 데몬은 그대로 둬도 됨.)

## 실사용 검증 체크리스트
각 인스턴스 콘솔에서:
- [ ] 채팅 "보유 알려줘" → **aggressive=HD, balanced=HON, conservative=GILD** (RTX/TMO 없음).
- [ ] "계좌 요약" → equity가 사이드바와 일치(aggressive ~79,651 / balanced ~75,928 / conservative ~51,254).
- [ ] 사이드바 Holdings와 채팅 답변이 **일치**(이전엔 불일치였음).
- [ ] (있으면) alpaca provider 인스턴스는 채팅 계좌툴이 기존대로 Alpaca 계좌를 보여줌(불변).

## 알려진 한계
- account_farm에서 `get_orders`는 데몬 snapshot의 **미체결(open) 주문만** — 체결/취소 히스토리는
  미지원(사이드바·데몬 로그 참조). `get_portfolio_history`도 미지원 안내(현재 equity는 get_account_info).
- snapshot은 데몬 발행 주기(±수분) 기준 — alpaca의 "live"보다 약간 지연될 수 있으나 **계좌는 정확**.
- provider 감지는 `AUTOSTOCK_BROKER_PROVIDER` env(prod-run.sh가 account_farm 인스턴스에 주입).
  settings.yaml만으로 account_farm을 켠 경우(env 미설정)는 감지 안 됨 — prod-run.sh 경로에선 항상 주입됨.

## 별건 (옵션, 미포함)
- 옛 호스트 Alpaca 데몬은 종료됨(사용자 A 실행). 그 **Alpaca 계좌의 RTX/TMO + resting order는
  무관리로 잔존**(페이퍼). 원하면 flatten/cancel 별도 정리 가능(F94 범위 외).
