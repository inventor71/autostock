# Tech Stack Decisions — F30 (U1 + U2)

> 원칙: **기존 스택 재사용**, 신규 인프라 없음. 단일 언어(Python 3.11+).

## TS-1. 언어 / 런타임
- Python 3.11+ (기존). 신규 런타임 없음.

## TS-2. KIS 연동
- **KIS 공식 SDK(open-trading-api / `kis_auth`)를 git dependency로 핀**(커밋 고정, SECURITY-10).
  - 결정: Q5(Requirements)=A 공식 SDK. import 경로(`kis_auth`/`pykis`)는 **Code Gen 직전 검증**(이월).
- HTTP timeout: 기존 `install_session_timeout` 패턴 재사용/이식(SDK가 requests 세션 노출 시 동일 주입; 아니면 동등 래퍼).
- 자격증명: `KIS_PAPER_{APP_KEY,APP_SECRET,ACCOUNT}` / `KIS_LIVE_*` 환경변수(pydantic Settings).

## TS-3. Universe (U2)
| 소스 | 기술 | 비고 |
|---|---|---|
| KR base | KIS ETF 구성종목 API(KODEX200+코스닥150) | KisDataProvider/토큰 재사용. 폴백=시총 top-N |
| US base | pandas `read_html`(기존 dep) + yfinance `marketCap`(기존 dep) | S&P100 동적, top_n=100 |
| 스냅샷 | repo JSON(`config/universe/{kr,us}_base.json`) | 커밋, fallback |
- **신규 dependency 없음** — pandas/yfinance 모두 기존 `pyproject.toml`에 존재.

## TS-4. 테스트
- pytest + **Hypothesis**(기존 optional-dep `hypothesis>=6.0`) — PBT Partial.
- KIS/외부 fetch는 모킹. PBT는 순수 함수(round_to_tick, qty floor, universe dedup/normalize) 중심.

## TS-5. 스케줄 / 타임존
- 기존 `TradingScheduler`(APScheduler) 타임존 파라미터화 — `Asia/Seoul` 추가. 신규 라이브러리 없음.

## TS-6. 명시적 비결정 / 검증 이월 (Code Gen 직전)
- KIS SDK import 경로 + 모의 rate limit 정확값.
- KR ETF 구성종목 tr_id(미가용 시 시총 랭킹 폴백).
- US S&P100 read_html 소스 URL/표 구조.
