# F88 / U3 — BrokeredFetcher construction record

## 설계
- `BrokeredFetcher(signal_resolver, http_get, webfetch_allowlist)` — DI로 decoupled(테스트는 fake).
- `build_ctx(sources)` → JSON-able ctx dict. `_meta`(built_at, source keys) + 소스별 key.
- **signal**: 주입된 `signal_resolver(name, params)` 호출(daemon이 실제 SignalCollector로 배선 — U4/U5).
- **webfetch**: host가 도메인 allowlist(정확/서브도메인)에 있어야 함(SSRF 가드) → `http_get(url)` →
  `{status, body(32KB cap), host}`. allowlist 밖 → `_error`.
- **fail-honest**: 소스 실패는 `ctx[key] = {"_error": ...}`로 *표면화*(predicate가 결측 인지) —
  build_ctx는 소스 실패로 안 죽음. websearch는 미포함(후속).
- `default_http_get()` — httpx 기반 보수적 GET(lazy import, daemon-side only).

## 검증 (tests/triggers/test_fetch.py)
**10 passed** — signal 매핑·params 전달·resolver 에러 fail-honest·webfetch allowlist 통과/차단·
body cap·http 에러 fail-honest·한 소스 실패가 다른 소스 안 죽임·서브도메인 매칭.

## Security 컴플라이언스 (U3)
SECURITY-07(webfetch 도메인 allowlist=SSRF 가드), 15(fail-honest/예외 격리), 05(소스 shape는 U1
SourceRef 검증). predicate는 여전히 net 0(daemon이 대신 fetch).

## 파일
- 신규: `src/agent/triggers/fetch.py`, `tests/triggers/test_fetch.py`. 수정: `__init__.py`.
