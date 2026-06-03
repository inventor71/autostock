# Functional Design — Universe Provider 도메인 엔티티 (U2)

## E-1. BaseUniverseProvider (추상)
```
BaseUniverseProvider:
  market: str                       # "kr" | "us"
  cache_ttl: timedelta = 1 day
  get_symbols() -> list[str]        # base ∪ enabled themes, dedup+정렬
  _fetch_base() -> list[str]        # 추상: 동적 base 조회
  _load_themes() -> dict[str, list[str]]
  _load_snapshot() / _save_snapshot(list[str])
```

## E-2. KRUniverseProvider
```
KRUniverseProvider(BaseUniverseProvider):
  market = "kr"
  source = "etf_pdf"                # KODEX200 + KODEX 코스닥150 구성종목 (KIS)
  fallback = "marketcap_topn"       # 엔드포인트 미가용 시
  deps: KIS API client (토큰 공유 또는 KisDataProvider 재사용)
```

## E-3. USUniverseProvider
```
USUniverseProvider(BaseUniverseProvider):
  market = "us"
  source = "sp100_read_html"        # pandas.read_html
  rank = "yfinance_marketcap"       # 선택, top_n=100
  deps: pandas(read_html), yfinance (둘 다 기존 dep)
```

## E-4. Universe config 스키마 (settings.yaml)
```
universe:
  market: str                       # 활성 시장
  top_n: int = 100                  # US 랭킹 컷(선택)
  enabled_themes: list[str]
  themes:
    kr: { <name>: [code,...] }
    us: { <name>: [ticker,...] }
snapshot:
  kr: config/universe/kr_base.json
  us: config/universe/us_base.json
```

## E-5. 기존 모델/주입점 영향
| 위치 | 변경 |
|---|---|
| `config/settings.yaml` `trading.symbols` | universe 구조로 네이티브 이관(정적 리스트 제거) |
| `src/trading/engine.py:41` `self.universe` | provider.get_symbols() 공급 |
| `src/agent/orchestrator.py` `universe` | 동일 출처 주입(현 list[str] 시그니처 유지) |

## E-6. 에러 타입
- `UniverseError`: base+스냅샷 모두 비어있을 때(fail-closed). 트레이딩 진입 차단.
