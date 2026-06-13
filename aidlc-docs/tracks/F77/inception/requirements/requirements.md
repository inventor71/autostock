# F77 — StockTwits 리테일 sentiment 신호: 요구사항

**Track**: F77 · **Depth**: Standard · **Date**: 2026-06-13
**확정 방향** (사용자 답변): 범위 **B**(시간당 스윕 + 히스토리 + 브리프; wake 트리거는 후속), Security Baseline=Yes, PBT=Partial

---

## 1. 의도 분석 (Intent)

리테일 sentiment를 신호로 쓰고 싶다. 소스 비교(StockTwits vs 토스 커뮤니티 vs 기타,
2026-06-12~13 대화) 결과 **StockTwits**로 결정 — 근거:
- **작성자 자가 라벨** (`entities.sentiment.basic: Bullish|Bearish`) — NLP 추론 없이
  명시적 감성, LLM 분류 비용 0.
- 무인증 공개 심볼 스트림(`api.stocktwits.com/api/2/streams/symbol/{SYM}.json`,
  최근 30개 메시지) **라이브 확인 완료** — 무인증 한도 ~200 req/hr라
  131심볼 유니버스 시간당 1스윕이 한도 안에 들어감.
- S&P100 전 종목 커버리지 (토스 커뮤니티는 인기주 편중 + 비공식 크롤링 리스크).

**핵심 원칙**: sentiment는 절대값이 아니라 **자기 베이스라인 대비 변화**가 신호
(StockTwits는 평상시 ~70-80% Bullish 낙관 편향). 따라서 히스토리 축적이 1급 요구사항.

## 2. 현재 상태 (통합 지점)

| 위치 | 역할 |
|---|---|
| `src/signals/` (F61) | SignalCollector — sources/ 플러그인(alpaca_news, finnhub_earnings), fail-honest + degraded_sources, TTL 캐시, 브리프 조립(brief.py) |
| `src/signals/settings.py` | `settings.yaml` `signals:` 블록 — 임계값은 코드 아닌 설정(FR-7 선례) |
| `src/trading/modes/agent.py` | 데몬 스케줄러 잡 등록부 (`add_seconds_job`/`add_daily_job`/`add_market_*_job`) |
| `src/agent/orchestrator.py` | research/intraday 턴에 브리프 prepend |
| `workspace/` | 파일 기반 영속화 관례 (JSONL, ET 날짜 키 — F72 screening 선례) |

## 3. 기능 요구사항 (FR)

### FR-1: StockTwits 소스 (`src/signals/sources/stocktwits.py`)
- 심볼당 무인증 GET → 최근 30개 메시지에서 **자가 라벨만 집계** (메시지 본문은
  신호화에 사용하지 않음): `bullish_n`, `bearish_n`, `untagged_n`, 최신 메시지 id/ts.
- HTTP 오류/형식 변화/차단 → 해당 심볼 skip, 소스 전체 실패 → `degraded_sources`
  등록 (F61 fail-honest 관례). **공식 보장 없는 엔드포인트라는 전제로 설계** —
  깨지면 조용히 degraded, 절대 턴/데몬을 막지 않음.
- 한도 준수: 스윕당 요청 간 간격(예: ≥0.3s) + 시간당 총량이 200을 넘지 않게.

### FR-2: 시간당 유니버스 스윕 + 히스토리 영속화 (데몬)
- 데몬 스케줄러에 **시간당 1회** 전 유니버스 스윕 잡 추가 (LLM 비용 0, HTTP 131회).
  장중/프리장에만 돌리는 시간 창은 설정으로 (기본: ET 04:00–20:00).
- 스윕 결과를 `workspace/sentiment/` 아래 JSONL로 append (ET 날짜 키, F72 선례):
  심볼별 `{ts, symbol, bullish_n, bearish_n, untagged_n}`.
- 중복/정지 대비 멱등: 같은 시간대 재실행은 단순 append (읽기 측이 시간순 처리).

### FR-3: 베이스라인 + 이상치 선별 (순수 코어)
- 히스토리에서 심볼별 베이스라인(최근 N일 bull-ratio 평균/표준편차, 메시지량 평균)을
  계산하고 현재 스윕과 비교: `bull_ratio_z`, `volume_z`.
- **이상치 상위 K개**만 선별 (전 종목 나열 금지 — 브리프 비대화 방지).
  베이스라인 표본이 부족한 종목(콜드스타트)은 이상치로 선별하지 않음.
- 임계값/N/K는 `signals:` 설정 블록 (FR-7 선례).

### FR-4: 브리프 공급
- research 브리프(F61 `assemble_brief`)에 "Retail sentiment (StockTwits)" 섹션 추가:
  이상치 종목별 한 줄 (`SYM bull% (평소 대비 z), msgs (z), 방향`).
- intraday 브리프에는 보유/워치리스트 종목에 이상치가 있을 때만 해당 종목 라인 포함.
- 이상치 없으면 섹션 생략 (노이즈 최소화).

### FR-5: 범위 제외 (후속 트랙 후보)
- **wake 트리거 없음** (베이스라인 축적 후 별도 트랙 — 사용자 결정).
- 보유/워치리스트 분 단위 고빈도 폴링 없음 (시간당 스윕만).
- 메시지 본문 LLM 분석 없음 (라벨 집계만).
- TUI 노출(steer_read verb) 없음 — 브리프 경유로 충분, 필요 시 후속.

## 4. 비기능 요구사항 (NFR)

- **NFR-1 (fail-honest)**: 소스/스윕/베이스라인 어느 단계의 실패도 research·intraday
  턴과 데몬 스케줄러를 깨지 않음. 스윕 잡 예외는 로그 후 다음 tick 대기.
- **NFR-2 (ET 날짜 일관성)**: 히스토리 파일 키는 ET trading date (`compute_et_date`).
- **NFR-3 (레이트 예산)**: 시간당 요청 총량 ≤ 150 (200 한도의 여유분) — 스윕 1회
  131 + 재시도 여유. 429/403 감지 시 해당 스윕 중단(백오프), 다음 시간 재개.
- **NFR-4 (저장 위생)**: 사용자명/메시지 본문 저장 안 함 — 집계 숫자만 (개인정보 無,
  SECURITY-03). 외부 응답은 스키마 검증 후 사용 (타입/범위 — SECURITY-05).
- **NFR-5 (보존)**: JSONL 일별 파일, 회전 없음 (기존 workspace 관례). 베이스라인
  계산은 최근 N일만 읽음.

## 5. Extension 룰 적용 매핑

**Security Baseline (Enabled)**:
- SECURITY-03: Loguru 로깅, 개인정보(닉네임/본문) 미저장 → NFR-4.
- SECURITY-05: 외부 JSON 응답 스키마 검증(pydantic), 심볼 문자열 정규화 → FR-1/NFR-4.
- SECURITY-15: 모든 HTTP/파일 I/O try-except, fail-honest/fail-closed → NFR-1/3.
- SECURITY-07/10: 신규 외부 통신은 api.stocktwits.com HTTPS 단일 출처, 신규 의존성
  없음(stdlib/requests 기존 스택) — 준수 확인 대상.
- 나머지: N/A (신규 인증/암호화 자산/배포 인프라 없음).

**PBT (Enabled — Partial)**:
- 라벨 집계·bull-ratio·z-score 순수 함수 property test (임의 카운트 → 범위/부호 불변식).
- 히스토리 레코드 직렬화 round-trip.

## 6. 수용 기준 (Acceptance)

1. 데몬 기동 후 시간 창 내 매시 스윕이 돌고 `workspace/sentiment/<ET날짜>.jsonl`에
   131심볼 집계가 append된다 (라이브 스모크).
2. 며칠치 히스토리(또는 합성 데이터)에서 베이스라인 대비 이상치 상위 K개가 선별되고,
   research 브리프에 섹션으로 들어간다 (콜드스타트 종목은 제외됨).
3. StockTwits 차단/오류 주입 시: 스윕은 백오프로 중단, 브리프는 섹션 생략 +
   degraded_sources 표기, 턴/데몬 정상.
4. 시간당 요청 총량이 150을 넘지 않는다 (테스트로 카운트 검증).
5. 저장 파일에 사용자명/메시지 본문이 없다.
