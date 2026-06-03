# Functional Design — Universe Provider 비즈니스 로직 모델 (U2)

> Q6 답변으로 추가된 unit. 종목 풀(universe)을 "어떻게 얻는가"를 분리.
> 발견: 현 US universe는 `config/settings.yaml`의 `trading.symbols` **정적 리스트**(동적 아님).
> 목표: base(동적) ∪ theme(사용자 설정) 합집합을 제공, 캐시 + 정적 스냅샷 fallback.

## 1. 구성

```
BaseUniverseProvider (추상)
  ├─ get_symbols() -> list[str]          # base ∪ enabled themes (dedup, 정렬)
  ├─ _fetch_base() -> list[str]          # 구현별 동적 조회 (추상)
  ├─ _load_themes() -> dict[str,list]    # config의 명명 테마
  └─ 캐시(TTL=1일) + 스냅샷 fallback
       │
   ┌───┴────────────────────────┐
KRUniverseProvider          USUniverseProvider
(KODEX200+코스닥150 ETF      (S&P100 read_html +
 구성종목, KIS API)           yfinance marketCap rank)
```

## 2. get_symbols() 흐름

```
get_symbols():
  base = _cached_base()                      # 1일 TTL
  themes = _load_themes()                     # config (enabled 목록)
  symbols = dedup(base ∪ ⋃ themes[enabled])
  return sorted(symbols)

_cached_base():
  if cache fresh(<1일): return cache
  try:    b = _fetch_base()                   # 동적 (KR=ETF PDF, US=S&P100)
          if b non-empty: save_snapshot(b); cache=b; return b
  except: pass
  return load_snapshot()                      # fallback: repo 정적 스냅샷
```

- **결정성/오프라인**: 동적 조회 실패(네트워크/rate-limit/장외)해도 스냅샷으로 항상 비어있지 않은 universe 반환(fail-safe).
- **리프레시**: 1일 TTL. 성공 시 스냅샷 갱신(다음 fallback 최신화).

## 3. base 동적 소스 (구현별)

### KRUniverseProvider — Q6 source = ETF 구성종목
- KODEX 200(069500) 구성종목 ≈ KOSPI200, KODEX 코스닥150 구성종목 ≈ KOSDAQ150.
- KIS ETF 구성종목 API로 두 ETF의 PDF(구성종목) 조회 → 합집합.
- 정확한 tr_id/엔드포인트 = **Code Gen 직전 검증**(미지원 시 시가총액 상위 N 랭킹으로 폴백 — BR 참조).

### USUniverseProvider — 기존 정적 trading.symbols를 동적으로 대체
- base = S&P 100 구성종목 **동적 조회**: pandas `read_html`(이미 dep)로 공개 구성종목 표 파싱.
- (선택) yfinance `marketCap`(이미 dep, `agent/tools/market.py:144` 사용처 존재)로 정렬/상위 N 컷.
- 실패 시 스냅샷(seed = 기존 curated 리스트에서 이관) fallback.

## 4. 테마 overlay (사용자 설정)

```yaml
# config/settings.yaml (예시 구조)
universe:
  market: kr            # 활성 시장 (kis 단독 실행 시 kr)
  enabled_themes: [반도체]
  themes:
    kr:
      반도체: ["005930", "000660", ...]   # 삼성전자, SK하이닉스 ...
    us:
      반도체: ["NVDA", "AMD", "AVGO", ...]
```
- 사용자가 `enabled_themes`로 켜고, `themes.<market>.<name>`으로 종목 extend.
- 테마는 **base에 더해짐**(합집합). base에 이미 있어도 dedup.

## 5. 기존 시스템 통합 (이관)

- 현 `trading.symbols` → universe provider로 대체. `engine.py:41 self.universe` / orchestrator `universe` 주입 지점을 provider.get_symbols()로 공급.
- monorepo-refactor-as-native: 정적 리스트를 새 구조로 **네이티브 이관**(마이그레이션 강조 주석 없이; 사연은 커밋 메시지). 기존 curated 종목은 US 스냅샷 seed + 필요 시 테마로 보존.
- KIS 단독 실행: `market=kr` → KRUniverseProvider 사용. (멀티마켓 동시 선택은 F33.)
