# Functional Design — Universe Provider 비즈니스 규칙 (U2)

## UR-1. get_symbols 합성
- 결과 = `dedup(base ∪ ⋃ themes[enabled_themes])`, 정렬(결정적 순서).
- 항상 **비어있지 않음** 보장: 동적 실패 시 스냅샷, 스냅샷도 없으면 `UniverseError`(fail-closed — 빈 universe로 트레이딩 진입 금지).
- ⚠️ **첫 실행 오프라인 방지(Critic MED-4)**: `config/universe/kr_base.json`·`us_base.json`을 **비어있지 않게 커밋**.
  US seed = 이관 시 기존 `trading.symbols` 캡처분, KR seed = 커밋된 초기 종목 리스트. (둘 다 없으면 첫 KR 실행이 UniverseError로 기동 실패.)

## UR-1a. trading.symbols 전면 재배선 (Critic MED-4 — 사용자 결정: 깨끗이 제거)
- `trading.symbols`를 읽던 **모든** 호출부를 provider로 교체: `main.py:135/305/354/455`,
  `intraday_collector.py:168`, `agent/tools/__main__.py:35`, `engine.py`/`orchestrator`.
- `--symbols` override: provider 결과를 명시 인자로 override(테스트용 부분집합) — 의미 보존.
- `config/config.py`의 `trading.symbols` 필드/기본값 제거(스키마에서 네이티브 삭제).

## UR-2. 캐시 / 리프레시
- base 캐시 TTL = **1일**. 만료 시 `_fetch_base()` 재시도.
- `_fetch_base()` 성공(비어있지 않음) 시에만 캐시/스냅샷 갱신. 실패 시 직전 스냅샷 유지(stale-but-safe).
- 스냅샷 위치: repo 내 `config/universe/{kr,us}_base.json`(또는 동등). 커밋 대상(결정적/오프라인 재현).

## UR-3. KR base (시가총액 상위 N — 2026-06-03 정정)
> Q6 답변은 "ETF 구성종목"이었으나 KIS OpenAPI에 KOSPI200/KOSDAQ150 **구성종목 전용 엔드포인트가
> 깔끔히 없음**(domestic 예제에 ETF-구성종목 부재; 지수는 카테고리 시세만). 대신 **`market_cap`(시가총액
> 상위 순위) 엔드포인트 존재** → 동적 base를 이걸로(폴백을 주 경로로 승격).
- KOSPI 시총 상위 ~200 + KOSDAQ 시총 상위 ~150 합집합(지수 구성의 동적 근사).
- 종목코드 6자리 문자열 정규화. 실패 시 스냅샷 fallback(UR-2).

## UR-4. US base (S&P 100)
- pandas `read_html`로 구성종목 표 파싱 → 티커 정규화(대문자, 클래스주 표기 통일 예: `BRK.B`→데이터 제공자 규약 일치).
- (선택) yfinance marketCap 정렬 후 상위 N(기본 100) 컷. marketCap 조회 실패 종목은 base 유지(드롭하지 않음).
- 실패 시 스냅샷(seed=기존 `trading.symbols`) fallback.

## UR-5. 테마
- `enabled_themes`에 나열된 이름만 활성. 미정의 테마 이름 → 경고 로그 후 무시(주문 흐름 비차단).
- 테마 종목도 base와 동일 정규화/dedup 적용.
- 시장별 분리: `themes.kr` / `themes.us`. 활성 `market`에 해당하는 테마만 적용.

## UR-6. 검증 / 안전
- 동적 소스 응답은 형식 검증(티커 패턴, 비어있지 않음) 후 채택(SECURITY-05 input validation).
- 외부 fetch는 timeout 적용(무한대기 금지). 네트워크 예외는 fallback 경로로(fail-safe).
- universe 크기 sanity(예: KR base가 비정상적으로 작으면 스냅샷 우선) — 동적 오염 방지.

## UR-7. PBT 대상 (PBT Partial)
- `get_symbols` 합성: dedup 멱등, base/theme 합집합 교환법칙, 결과 정렬 안정성(PBT-03 invariants).
- 티커 정규화: 멱등(`norm(norm(x))=norm(x)`)(PBT-02 round-trip 성격).
