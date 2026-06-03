# NFR Requirements — universe-provider (U2)

## UN-1. 성능
- `get_symbols()`는 **캐시 우선**(base TTL 1일). 동적 fetch는 캐시 만료 시에만 → 주문/리서치 hot path 비차단.
- 외부 fetch(KIS ETF / read_html / yfinance)는 **timeout 적용**, 비동기 아님(주기적 1회).

## UN-2. 신뢰성 / 가용성
- **항상 비어있지 않은 universe 보장**: 동적 실패 → 스냅샷 fallback. 둘 다 비면 `UniverseError`(fail-closed, 빈 풀로 트레이딩 진입 금지).
- 동적 응답 **sanity 검사**(크기/형식) — 비정상 축소 시 스냅샷 우선(오염 방지).
- stale-but-safe: fetch 실패 시 직전 스냅샷 유지.

## UN-3. 보안 (Security extension)
| 규칙 | 적용 |
|---|---|
| SECURITY-05 (input validation) | 외부 종목 응답 티커 패턴/비어있음 검증 후 채택 |
| SECURITY-09 (fail-safe) | fetch 예외 → fallback 경로 |
| SECURITY-10 (dependency pinning) | pandas/yfinance 기존 핀 사용, 신규 dep 없음 |
| SECURITY-15 (fail-closed) | 빈 universe 차단 |
- 외부 소스 신뢰 경계: read_html 결과는 형식 검증 후만 사용(임의 콘텐츠 직접 신뢰 금지).

## UN-4. 유지보수 / 테스트 (PBT Partial)
- `get_symbols` 합성: dedup 멱등, 합집합 교환법칙, 정렬 안정성.
- 티커 정규화 멱등성. 외부 fetch 모킹(결정적 테스트).

## UN-5. 설정 / 운영
- 테마/스냅샷/활성 market은 `config/settings.yaml` `universe.*`로 운영 변경(코드 변경 불필요).
- 리프레시 주기(1일) 설정화 가능.
