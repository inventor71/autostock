# F20 Application Design Plan

> 기반: `requirements/requirements.md` (16개 Alpaca MCP stock-only read tools, TS 인프로세스)
> 기존 패턴: `FileDrop`(env 로딩, hasToken 체크), `handleStructured`(Zod→핸들러→텍스트 응답)

## 설계 범위

신규 컴포넌트 1개 + 기존 파일 수정 1개:
- **`operator-console/src/alpaca-data.ts`** (신규) — Alpaca REST v2 HTTP 클라이언트
- **`operator-console/src/mcp-server.ts`** (수정) — 16개 읽기 도구 등록

---

## 질문

### Q1. Alpaca 키 누락 시 동작

`ALPACA_API_KEY` / `ALPACA_API_SECRET` 환경변수가 없을 때:

- A) **MCP 서버 시작 허용, 읽기 도구 호출 시 오류 반환** — 쓰기 도구는 정상 작동. Alpaca 읽기 도구는 호출 시점에 "Alpaca API key not configured" 반환. (FR-2에 명시된 방식, 권장)
- B) **MCP 서버 시작 거부** — 읽기 도구가 필요한 환경이므로 키 없으면 fail-fast. 단, 쓰기 도구까지 사용 불가.
- C) 기타

[Answer]: B

### Q2. AI 소비용 텍스트 포맷

Alpaca JSON 응답을 MCP `text` content로 변환할 때:

- A) **마크다운 테이블 / 불릿 리스트** — AI가 가장 잘 파싱. 예: `| AAPL | $195.83 | 2024-06-15T16:00:00Z | NASDAQ |` 형식의 표. (권장)
- B) **자연어 산문** — "AAPL last traded at $195.83 on NASDAQ at 4:00 PM ET." 사람이 읽기 좋지만 AI가 수치를 파싱하기 어려움.
- C) **Key-value 구조 텍스트** — `symbol: AAPL\nprice: 195.83\ntimestamp: ...` 형식. JSON과 유사하나 더 읽기 쉬움.
- D) **Raw JSON 그대로** — Alpaca 응답을 최소한의 정리만 해서 전달. 가장 많은 정보를 보존하나 컨텍스트 토큰 소모가 큼.
- E) 기타

[Answer]: A

### Q3. 단일/다중 심볼 Zod schema 방식

Alpaca MCP는 `symbol_or_symbols` 파라미터에 comma-separated string을 사용합니다. Zod 스키마에서:

- A) **`z.string()` + 내부 split/trim** — Alpaca MCP 정확 매칭. "AAPL,MSFT,TSLA" 그대로 전달 가능. AI가 comma-separated를 잘 이해함.
- B) **`z.array(z.string())` + 내부 join** — Zod가 배열 요소를 개별 검증. 프론트엔드 친화적이나 Alpaca MCP 시그니처와 달라짐.
- C) 기타

[Answer]: A (zod 관련해서는 F21에서도 현재 다루고 있으니 머지할때 유의해서 zod schema가 통일성이 있는지 추가 확인)
