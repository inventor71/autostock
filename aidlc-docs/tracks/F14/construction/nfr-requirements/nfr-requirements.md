# F14 NFR Requirements (minimal)

## 신규 런타임 의존성: 0
- A: `requests`는 alpaca-py가 이미 사용(transitive). 신규 추가 없음.
- B: stdlib threading / 기존 APScheduler 재사용.
- C: 기존 launcher(bun/TS) 재사용.

## NFR 값 (Requirements §5 확정)
- HTTP 타임아웃: connect 3s / read 5s (모든 Alpaca 호출).
- prefetch 주기: 가격 5s / 바 60s.
- self-heal: patience 3분(advance 0회) / restart 후 health-wait 60s / restart 1회.

## 동시성 (NFR-2 보존)
- prefetch 워커는 **read-only**(가격/바 조회)이므로 broker mutation 단일 워커(CommandBus)와 **분리**한다.
  CommandBus에 얹지 않음. detect_wakes는 캐시만 read.
- self-heal restart는 systemd 단위 재시작 → 라이브 데몬 이중기동 불가(NFR-1).

## ⚠️ alpaca-py 0.43.2 타임아웃 API 실측 결과 (Q-A2 확정)
실측(venv/bin/python):
- `TradingClient`/`StockHistoricalDataClient`/`RESTClient` 생성자에 **timeout 파라미터 없음**(전부 False).
- `RESTClient._request`는 timeout을 전달하지 않음.
- 내부 HTTP는 `client._session`(진짜 `requests.Session`) 사용 — 확인됨(`isinstance` True).
- → **Q-A2=A(SDK 파라미터) 불가 → B(세션 레벨 주입)로 확정**: 클라이언트 생성 후 `client._session.request`를
  래핑해 호출자가 timeout 미지정 시 `timeout=(3,5)` 기본 주입(지정 시 존중).

## PBT
- 이번엔 advisory(순수 판정 로직 일부만). 차단 아님.
