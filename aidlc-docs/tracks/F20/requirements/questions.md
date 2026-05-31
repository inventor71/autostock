# F20 요구사항 확인 질문 (Requirements Verification)

> 트랙: **F20 — 임의 종목 읽기 도구(Alpaca-shaped read tools)**
> 각 질문의 `[Answer]:` 태그 **바로 뒤에** 선택지(A/B/...) 또는 자유 서술로 답해 주세요.
> 모든 답이 채워지면 이 답을 근거로 `requirements.md`를 작성합니다. (참고: [[f9-gated-alpaca-orders]] §5 — F9에서 읽기 도구는 의도적으로 보류됨)

## 배경 (왜 이 트랙인가)
콘솔은 F9로 **주문(쓰기)** 은 구조화된 Alpaca-shaped 도구로 낼 수 있게 됐지만, **읽기**는 여전히
`steer_read`(데몬이 써둔 `snapshot.json`/`monitor.json`을 단방향 FileDrop으로 읽는 경로)만 있습니다.
그래서 운영자가 "MSFT 현재가?" 처럼 **보유/대기 주문에 없는 임의 종목**을 물으면 AI가 호출할 도구가
없어 답을 못 합니다. 이 트랙은 **읽기 전용(주문 권한 없음)** Alpaca-shaped 시세/조회 도구를 추가합니다.

---

## Q1. 추가할 읽기 도구의 범위
어떤 Alpaca-shaped 읽기 도구를 추가할까요? (advisor-only, 비변경)

- A) **시세만 (최소)** — `get_stock_quote`(또는 latest trade) 1~2개. "현재가?" 질문 해결에 집중.
- B) **시세 + 포지션/주문 조회 (권장)** — `get_stock_quote` + `get_orders`(임의 상태 필터) + `get_positions`.
  현재 `/book`은 보유·대기 종목만 보여주는데, 임의 종목 시세와 함께 전체 주문/포지션 조회를 Alpaca 표준 형태로 노출.
- C) **전체 읽기 표면 미러링** — 위 + `get_stock_bars`(과거 봉) + `get_latest_trade` 등 Alpaca MCP 읽기 도구 1:1 미러.
- D) 기타 (아래 서술)

[Answer]: C-2 (stock-only 실용 서브셋, Alpaca MCP 공식 이름·파라미터 1:1 매칭. crypto/options/watchlist/corporate actions 제외. 2026-05-31 후속 논의로 구체화)

## Q2. 시세 데이터 경로 (핵심 아키텍처 결정)
임의 종목 시세를 어디서 가져올까요? 현재 FileDrop은 **단방향**(콘솔→데몬 명령 append, 데몬→콘솔 snapshot 단순 읽기)이라
요청/응답 상관(correlation) 채널이 없습니다.

- A) **콘솔 인프로세스 (TS에서 Alpaca 데이터 API 직접 호출)** — MCP 서버(bun/TS)가 Alpaca data API를 직접 호출.
  빠르고 데몬 왕복 없음·신규 데몬 코드 없음. 단, **콘솔 MCP env에 Alpaca 데이터 자격증명 주입 필요**
  (F18은 `AUTOSTOCK_ROOT`+토큰만 배선, 데이터 키는 아직 없음) + 파이썬 시세 경로를 TS에 일부 중복.
- B) **데몬 요청/응답 왕복** — 콘솔이 읽기 요청을 file-drop → 데몬이 `get_latest_prices`로 조회 → 응답 파일을
  콘솔이 폴링. 파이썬 시세 경로·자격증명 재사용(단일 진실원). 단 **요청/응답 상관 채널을 신규 구축**해야 함(현재 없음).
- C) **스냅샷 워치리스트 확장** — 데몬이 설정된 watchlist 종목 시세를 주기적으로 `snapshot.json`에 포함, 콘솔은 스냅샷만 읽음.
  신규 채널 불필요하나 **"임의 종목" 요건은 미충족**(애드혹 종목은 못 봄). A/B의 보조로만 의미.
- D) 기타 (아래 서술)

[Answer]: A

## Q3. 시장 마감 시 동작
정규장 마감 후 "현재가?"에 무엇을 돌려줄까요?

- A) **마지막 체결(last trade) 우선** — 마감 시 최근 체결가 반환, 데이터 시각(timestamp)을 함께 표기.
- B) **호가(quote, bid/ask) 우선** — 마감 시 마지막 호가. (마감엔 stale일 수 있음)
- C) **둘 다 반환** — last trade + bid/ask + 각 timestamp + `market_open` 플래그를 함께 돌려 AI가 판단.
- D) 기타 (아래 서술)

[Answer]: D. 종가로 명시하면 마감시 종가. 현재가는 (시간외 체결 포함, 마지막 체결가) 

## Q4. 게이팅(권한) 정책
읽기 도구는 비변경(no order authority)입니다. opencode 권한 키를 어떻게?

- A) **`allow` (권한 프롬프트 없음)** — `steer_read`와 동일. 비변경이므로 사람 확인 불필요. (권장)
- B) **`ask` (매 호출 사람 확인)** — 보수적. 단 읽기마다 확인은 운영 흐름을 끊음.
- C) 기타 (아래 서술)

[Answer]:A

## Q5. 데이터 피드 / 레이트
Alpaca 무료 IEX 피드로 충분한가요, 아니면 고려할 제약이 있나요?

- A) **IEX 무료 피드로 충분** — 현재 `get_latest_prices`가 쓰는 것과 동일. 레이트 한도는 운영 규모상 비고려.
- B) **SIP/유료 피드 필요** 또는 레이트/쿼터를 명시적으로 설계에 반영해야 함 (아래 서술).
- C) 기타 (아래 서술)

[Answer]: A

## Q6. 서브모듈(포크) 권한 키 반영
새 읽기 도구는 F19처럼 포크 opencode 설정(`operator-console/cli/{opencode.json,.opencode/opencode.jsonc}`)에
권한 키를 추가해야 합니다. 이번 트랙에서 **함께** 처리하는 것으로 확정할까요?

- A) **예 — 같은 트랙에서 서브모듈 브랜치까지 처리** (state.md 가정과 일치, 권장).
- B) 아니오 — 별도 후속 트랙으로 분리 (이유는 아래 서술).

[Answer]: A

---

## 확장(Extensions) 옵트인
다음 확장을 이 트랙에 적용할지 선택해 주세요. (해당 답을 `aidlc-state.md`의 Extension Configuration에 기록)

### EX1. Security Baseline
읽기 도구가 시세 데이터/자격증명을 다루므로 보안 베이스라인(입력 검증, 자격증명 취급, 최소 권한 등) 적용 여부.

- A) 예 — Security Baseline 적용
- B) 아니오 — 미적용

[Answer]: A

### EX2. Property-Based Testing
읽기 도구 파서/포맷터에 속성 기반 테스트(property-based testing) 적용 여부.

- A) 예 — 적용
- B) 아니오 — 미적용 (예시 기반 단위 테스트로 충분)

[Answer]: A

---

## 추가로 남기고 싶은 메모 (선택)
[Answer]:
