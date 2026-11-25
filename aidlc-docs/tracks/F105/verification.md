# F105 검증

## 변경과 검증 범위

정상 모드(steering on/off)와 dry 모두 IntradayContext를 사용한다. 계좌 상태, 보유 종목,
구조화 watch, watchlist.md에서 유니버스에 해당하는 최대 12개 추가 관찰 후보와 시장 지표를
조회한다. 문서의 종목 언급을 거래 조건으로 해석하지 않으며 매매 유니버스를 확장하지 않는다.
dry의 morning signal brief도 같은 collector에 연결하고 frozen universe를 그대로 전달한다.

뉴스는 설정된 공급자를 사용하고 실패/오래된 기사에는 configured fallback을 시도한다.
정상 빈 결과, 조회 실패, 오래된 기사, 발행일 미상, 미조회는 구분된다. cached fetch 시각을
현재 시각으로 덮어쓰지 않는다. 뉴스는 15분 poll 사이에 삭제하지 않고 턴에 전달할 때까지
누적한다. 뉴스 기다림은 최대 10초이며 느린 공급자를 위한 중복 worker를 만들지 않는다.
이 제한은 전체 브리프 실행시간 제한이 아니다: 시세/봉 조회 시간은 추가된다.

시그널 CLI는 실제 Settings.universe 또는 dry의 frozen universe를 사용한다. 수집 날짜는
호스트 날짜 대신 미국 ET 날짜를 사용한다. quote의 기존 price는 1d bar_close로 명시하고
별도 latest_quote에 최신 가격과 원천 시각을 제공한다. indicators/scoreboard/movers/macro에도
기준 시각을 전달한다. 저품질 정보를 없다고 단정하지 않고 결정에 필요한 부분만 추가 조사한다.

## 자동 검증

F105 worktree에서 main의 Python 3.12 venv 사용:

```bash
/home/jihoonpark/Project/autostock/venv/bin/python -m pytest -q
```

**1,860 passed**, 기존 warning 30개. baseline 1,834 대비 26개 검증 추가.
핵심 regression은 실제 설정→movers/earnings/IPO/news CLI, frozen dry universe, provider
실패와 복구, 기사 원천 날짜와 조회 날짜 분리, 여러 poll 사이의 unread 보존, 느린 뉴스 공급자,
두 정상 실행 경로의 프롬프트 갱신, 실제 dry builder의 계좌/설정 불변이다.
전체 테스트 중 발견한 신규 테스트의 AGENT_JOURNAL_ROOT 누수도 fixture에서 복원했다.

신규 모듈/테스트 Ruff 전체 통과. 기존 수정 파일은 baseline Ruff 진단 140개가 있어 비교
검증했으며 **추가 진단 0개**, git diff --check 통과. 전역 기존 lint 부채 정리는 범위 밖이다.

## 실제 데이터 확인 (실제 주문·모델 호출 없음)

2026-11-25 09:40~09:47 KST, 별도 private 산출물에만 기록했다.

- Toss QQQ: 전일 일봉(11/24)과 현재 last price의 source timestamp(11/25 KST)를 구분.
- 실제 설정으로 movers/earnings 도구 동작, Finnhub calendar 정상 조회. 최초 간단 점검 2.43초.
- Opus book 기반 20종목 브리프: 16.11초. 가격/봉 조회 실패 0, 가격 원천 시각 미상 0.
  일부 소액 종목의 60초 초과 시세, 오래된 뉴스, 10초 뉴스 대기 시점의 미완료 항목을 노출.
- Alpaca QQQ 최신 기사는 11/7, GOOGL 결과는 0, SNDK 최신은 11/23이었다. Yahoo fallback은
  YFDataException. 따라서 코드 수정만으로 모든 종목의 당일 뉴스를 확보했다고 볼 수 없다.
- Alpaca exclude_contentless true/false를 비교했으나 위 세 종목의 결과는 같았다.
  효과 근거가 없는 필터 변경은 하지 않았다.

private 결과: research-comparisons/F105/{live-smoke.json,news-content-filter.json,live-context/}.
live-context의 full-ledger 비교는 실행 중인 기존 poller의 정상 metadata 갱신도 포함하므로
false였다. 이는 장부 불변 테스트로 사용하지 않는다. 적용 전후 계좌 경제 상태와 모델 기록의
보존은 별도 백업/재시작 검증으로 확인한다. 자동 테스트에서는 실제 builder를 통한 전체 장부
불변을 검증했다. API 점검은 읽기 전용 client로만 수행했다.

수익률 개선은 이 테스트들의 결론이 아니다. 다음 거래 세션부터 같은 비용·동일 모델 설정의
dry 기록에서 거래 의도, 실제 가상 체결, 정보 공백, 비용 차감 수익을 함께 비교해야 한다.
