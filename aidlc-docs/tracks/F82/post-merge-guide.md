# F82 — Post-Merge Guide (Intraday 자동 수집)

## 무엇이 바뀌나
- 에이전트 데몬이 이제 **intraday 세션 피처를 자동 수집**한다:
  - **기동 시**: 유니버스(US ~100종목) 각 종목의 `data/intraday/<SYM>.parquet` 커버리지를 보고
    부족분을 **백그라운드 스레드로 백필**(기본 3년, Alpaca 분봉).
  - **매 장마감(EOD)**: 그날 세션을 유니버스 전체에 대해 append.
- 기본 **ON** (`intraday_collection.enabled: true`).
- 의존: F80(Parquet store). F80 → F82 순서로 머지.

## 전제조건
- **F80 머지 선행** (Parquet store + pyarrow). `pip install -e .` 로 pyarrow 설치돼 있어야 함.
- **Alpaca 자격증명** (`ALPACA_API_KEY`/`ALPACA_API_SECRET`) — 기존 운영 키 그대로 사용(신규 없음).
- **데몬 재시작** 후 적용. 재시작 직후 백필 스레드가 도므로 첫 기동은 Alpaca 호출이 한동안 발생
  (백그라운드라 데몬/트레이딩은 정상 동작).

## 실사용 검증 체크리스트
1. 데몬 로그에서 `intraday auto-collection enabled (provider=alpaca, backfill 3y, tf=5m)` 확인.
2. 잠시 후(백필 진행) `intraday backfill: N symbol(s), M session(s) written` 로그 확인.
3. `ls data/intraday/` → 유니버스 종목들의 `*.parquet` 생성 확인(처음엔 점진적으로 늘어남).
4. 장마감 후 로그 `intraday EOD collect: K session(s) across N symbol(s)` 확인.
5. 빠른 점검:
   ```bash
   python -c "from src.data.intraday.store import IntradayFeatureStore as S; s=S(); \
   print(len(s.symbols()),'symbols'); print(len(s.read()),'rows')"
   ```
   → 종목수가 유니버스 규모로 늘고 행수가 증가.
6. "정상" 모습: 종목당 수백~수천 행(세션/일), `date`는 `YYYY-MM-DD`, 값이 실제 OHLCV 범위.

## 튜닝 노브 (`config/settings.yaml` → `intraday_collection`)
- `enabled`: false로 끄면 백필·EOD 모두 미동작.
- `backfill_years`: 초기 백필 깊이(기본 3). 늘리면 첫 기동 Alpaca 호출↑.
- `provider`: `alpaca`(권장, 다년치) / `yfinance`(백필 ~60일로 degrade, 크래시 없음).
- `timeframe`: 세션 피처 산출 bar 간격(기본 5m).

## 용량 (실측 기반)
- 행=세션/일, 22컬럼, parquet snappy ~164 B/행.
- 3년 × ~100종목 ≈ **~12MB**, EOD 증가분 ≈ **~16KB/일(~4MB/년)**. 관리 불필요.

## 롤백
- `intraday_collection.enabled: false` + 데몬 재시작 (코드 롤백 불필요, 가장 빠름).
- 코드 롤백: F82 커밋 revert. 이미 쌓인 `data/intraday/*.parquet`는 그대로 유효(읽기 호환).

## 알려진 한계 / 범위 밖
- 백필은 **순차**(병렬화 없음) — 백그라운드라 startup 무영향이나 첫 완주에 수분 소요 가능.
- KR(KIS) 유니버스 intraday 수집은 미포함(US 전용).
- 분봉 원본(raw bars) 저장 안 함 — **세션 요약 피처만**.
- store는 upsert마다 종목 parquet을 통째 rewrite(현 규모에선 무의미한 비용).
- 데몬 provider가 yfinance일 때 백필은 ~60일까지만(Alpaca 권장).
