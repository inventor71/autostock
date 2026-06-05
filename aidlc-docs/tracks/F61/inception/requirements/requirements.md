# F61 요구사항 — 리서치 턴 주식 시그널 강화

## Intent Analysis
- **User request**: "autostock 리서치 턴이 주식 관련 시그널을 훨씬 더 잘 봐야 한다. 브로드컴(AVGO) 실적 폭락을 캐치하지 못했다 — 중요 가격 변동 뉴스와 시장 반응이 다른 종목에 미치는 영향을 고려하는 데이터 수집이 약하다."
- **Request type**: New Feature (Enhancement of existing research turn data collection)
- **Scope estimate**: Multiple Components (data providers, agent tools, prompts, orchestrator wiring, config)
- **Complexity estimate**: Moderate
- **Requirements depth**: Standard

## 배경 / 진단 (직전 분석)
AVGO는 거래 유니버스 안에 있었음(`config/settings.yaml`)에도 시그널 미포착. 코드 레벨 진단으로 확인된 구조적 공백:
1. 뉴스 = 종목별 pull + 에이전트 직접 호출 → 시장 전체 catalyst surfacing 없음 (`prompts.py`, `tools/market.py:news`)
2. 뉴스 소스 단일(yfinance) + 제목 키워드 감성 휴리스틱 (`news_provider.py`)
3. 전부 일봉 기반 → 애프터아워스/실적 갭 사각지대 (`tools/market.py`, `surge/detector.py`)
4. surge 감지기 = EOD·유니버스 한정·일봉·사후 기록 (선제 전파 없음)
5. **종목 간 전파(read-through/contagion) 모델링 전무** ← 사용자가 지목한 핵심
6. 실적 캘린더 awareness 부재 (per-symbol pull만)

## 확정된 결정 (Requirements Analysis Q&A)
| # | 항목 | 결정 |
|---|---|---|
| Q1 | 범위 | **A+B+C 묶음** — 종목 간 read-through 전파(A) + 시장 무버/catalyst 스캔(B) + 실적 캘린더 surfacing(C). D(AH 가격 캡처)/E(뉴스 소스 전면 교체)는 후속 트랙 |
| Q2 | 데이터 소스 | **Alpaca News(Benzinga)** = 뉴스 / **Finnhub 무료** = 실적 캘린더(Alpaca에 없음) / **yfinance** = 가격·펀더멘털·폴백 |
| Q3 | 전파 메커니즘 | **정적 피어 맵 + LLM 하이브리드** — Python이 정적 맵으로 영향 피어 후보를 좁혀 push, 최종 판단은 에이전트 |
| Q4 | 노출 방식 | **push + on-demand 툴 둘 다** — 리서치 프롬프트 앞단 prepend + 신규 툴 |
| Q5 | 유니버스 범위 | **거래 유니버스 + bellwether 워치리스트** (ETF·미편입 대장주 등 시그널 전용, 거래 불가) |
| Q6 | 검증 | **2-tier. Tier 1(자동·토큰 0)**: 유닛 + PBT + **다유형 과거 재현 코퍼스**(AVGO류 실적쇼크 + 섹터 동반락 + 매크로 쇼크 + 개별악재 비전파 + 오탐0 등 5~8 시나리오, 전부 결정적). **Tier 2(온디맨드·토큰)**: 에이전트 판단 품질 평가 하니스 — 수동 1회 트리거, **자동/CI 스위트엔 절대 미포함** |
| 확장 | Security / PBT | Security=**Disabled**, PBT=**Partial**(순수 함수/직렬화 round-trip) |

---

## Functional Requirements

### FR-1 — 시장 무버 스캔 (B)
- 거래 유니버스 + bellwether 워치리스트를 대상으로 **일중/일간 가격 변화율·거래량 비율·신규 뉴스 유무**를 한 번에 스캔하는 기능.
- 임계값(예: |chg| ≥ N%, vol_ratio ≥ M)을 넘는 "무버"를 추려 요약 산출.
- 결과는 (a) 리서치 턴 프롬프트 앞단에 push 되고 (b) on-demand 툴로도 호출 가능 (FR-5).
- 기존 `scoreboard`(유니버스 flat scan)와 중복되지 않게: 무버 스캔은 **임계 초과만 + 뉴스/전파 결합**으로 차별화.

### FR-2 — 뉴스 소스 업그레이드 (Alpaca News / Benzinga)
- 뉴스 1차 소스를 **Alpaca News API(Benzinga)** 로 전환·추가: 실시간 + 히스토리, 헤드라인/요약/링크/타임스탬프, 애프터아워스·실시간 catalyst 커버.
- 종목별 뉴스 + (가능하면) 시장 전체 뉴스 피드 활용.
- **yfinance 뉴스는 폴백으로 유지** (Alpaca 실패/미커버 시). 기존 `news` 툴 인터페이스는 호환 유지하되 소스 교체.
- 감성: 기존 제목 키워드 휴리스틱은 폴백으로 두되, Alpaca/Benzinga가 제공하는 메타(있으면)를 우선.

### FR-3 — 종목 간 read-through 전파 (A, 핵심)
- **정적 피어 맵**: 종목 → 섹터/연관군 매핑 테이블 (예: AVGO → 반도체 피어[NVDA, AMD, …] + AI-capex 군). config 또는 데이터 파일로 관리.
- 스캔(FR-1)에서 **큰 변동(임계 초과)이 감지된 종목**에 대해, 피어 맵으로 **영향 받을 수 있는 유니버스 내 종목(피어)** 을 도출.
- 도출된 read-through 후보를 **경고로 surfacing**(push + 툴). 최종적으로 "정말 영향이 있는가"의 판단은 에이전트에게 위임(LLM 하이브리드) — Python은 후보를 좁혀줄 뿐 결정하지 않음.
- 예: "AVGO −15% (실적 미스) → 반도체 피어 점검 권고: NVDA, AMD, QCOM, TXN; AI-capex 읽기: MSFT, GOOGL".

### FR-4 — 실적 캘린더 surfacing (C)
- **Finnhub 무료 `/calendar/earnings`** (날짜 범위)로 **유니버스 + 보유 종목**의 임박 실적(예: 오늘/내일/금주)을 집계.
- 리서치 턴에 "임박 실적" 목록을 사전 노출 + **보유 종목이 임박 실적 종목과 피어 관계면 read-through 점검을 유도**(FR-3 연계).
- per-symbol `earnings` 툴(기존, yfinance)은 상세 조회용으로 유지; FR-4는 aggregate 캘린더를 담당.

### FR-5a — 온디맨드 에이전트 판단 평가 하니스 (Tier 2 검증)
- 운영자가 **수동으로 1회** 실행하는 평가 하니스: 과거 시나리오(예: AVGO 폭락일)의 시그널 브리프를 에이전트에 주고, 에이전트가 read-through/무버 경고를 받아 내리는 판단(결정·근거)을 출력.
- **자동/CI 테스트 스위트에는 절대 포함되지 않음**(LLM 토큰 비용). 명시적 수동 트리거(예: `python -m ... eval-readthrough <SCENARIO>` 또는 스티어링 명령)로만 동작.
- 목적: Python 결정적 층(Tier 1)이 올린 후보가 "에이전트에게 실제로 유용한 판단으로 이어지는가"를 운영자가 필요할 때만 점검.

### FR-5 — 노출 (push + 툴)
- **Push**: Python이 무버(FR-1) + read-through(FR-3) + 임박 실적(FR-4)을 하나의 간결한 "시장 시그널 브리프"로 조립해 `morning_research_prompt`(및 multi-agent 변형) 앞단에 prepend. 에이전트가 반드시 보게 함.
- **Tool**: 신규 on-demand 툴 — 최소 `movers`(무버 스캔), `readthrough <SYM>`(특정 종목의 피어 영향), `earnings_calendar`(임박 실적). `python -m src.agent.tools <name>` 패턴 준수, JSON 출력.
- 두 경로는 동일 코어 로직을 공유(중복 산출 금지).

### FR-6 — 유니버스/워치리스트 범위
- 스캔 대상 = **거래 유니버스 ∪ bellwether 워치리스트**(config). 워치리스트 종목은 **시그널 전용**(거래 결정 대상 아님; 기존 `filter_in_universe`가 거래는 계속 차단).
- bellwether 예: SPY/QQQ/SMH 등 ETF, 미편입 대형주. 운영자가 config로 편집 가능.

### FR-7 — 임계값/설정의 config화
- 무버 임계(가격%·거래량비), 피어 맵, bellwether 리스트, 소스 토글(Alpaca/Finnhub/yfinance), 캐시 TTL을 **`config/settings.yaml`** 에 노출. 코드 하드코딩 금지.

---

## Non-Functional Requirements

### NFR-1 — Fail-honest / best-effort (차단)
- 어떤 데이터 소스 실패(레이트리밋·네트워크·키 부재)도 **리서치 턴을 크래시시키지 않음**. 부분 실패 시 graceful degrade(해당 시그널만 누락, 나머지 진행). 기존 `NewsPoller`·`scoreboard`의 best-effort 패턴 준수.
- 키 부재(예: `FINNHUB_API_KEY` 미설정) 시: 해당 기능을 조용히 비활성(가짜 데이터 금지, fail-honest) + 1회 경고 로그.

### NFR-2 — Bounded latency (스케줄러 보호)
- 모든 신규 HTTP 호출은 **타임아웃 바운드**(F14 `install_session_timeout` 패턴). 스톨된 소켓이 스케줄러 틱/데몬을 wedge하지 않아야 함.

### NFR-3 — 레이트리밋/캐시 준수
- Finnhub 60 calls/min, Alpaca 데이터 한도 준수. 무버/뉴스/캘린더는 적절한 TTL 캐시(기존 news 15분 TTL 류) + 배치/동시성으로 호출 수 최소화.

### NFR-4 — 결정성 (테스트 가능 코어)
- 피어 맵 해석, 변화율/무버 임계 판정, 시그널 레코드 직렬화는 **순수 함수**로 분리해 결정적·단위 테스트 가능하게. (PBT-Partial 대상)

### NFR-5 — 기존 동작 보존
- 기존 리서치/인트라데이/EOD 턴, surge/early-session, 숏(F54/F59/F60) 동작에 회귀 없음. prompts.py·tools/market.py·orchestrator.py 변경 시 기존 인터페이스 호환.

### NFR-6 — 키/시크릿 관리
- 신규 키는 **env-only**(`FINNHUB_API_KEY`), 코드/로그에 노출 금지. `.env` 네이밍 관행(F37) 준수.

### NFR-7 — Tier 2 토큰 보호 (차단)
- 에이전트 판단 평가 하니스(FR-5a / Tier 2)는 **자동 테스트·CI·정기 실행 경로에 절대 포함되지 않음**. 명시적 수동 트리거로만 LLM이 호출되어야 하며, 기본 `pytest`/CI run은 토큰을 한 푼도 쓰지 않아야 한다(구조적 분리: 별도 엔트리포인트 + CI에서 미수집되는 위치/마커).

---

## 검증 기준 (Q6) — 2-tier

**핵심 원칙**: 테스트 대상은 **Python 결정적 시그널 층**이지 LLM 판단이 아니다. FR-3에서 LLM에 위임하는 건 런타임 판단이며, "입력(가격/뉴스/맵) → 출력(무버·피어 후보·브리프)"은 LLM 없이 단언 가능하다. 따라서 **자동 검증은 토큰 0**.

### Tier 1 — 자동 / 토큰 0 (항상 실행, CI 포함)
- **유닛 테스트**: 합성 데이터로 무버 임계 판정·피어 맵 전파·시그널 브리프 조립·레코드 직렬화의 결정성 검증 (네트워크·LLM 불요).
- **PBT (Partial)**: 순수 함수에 Hypothesis 적용 — 변화율 계산 invariant(PBT-03), 레코드 직렬화 round-trip(PBT-02), 도메인 생성기(PBT-07), 시드 재현성(PBT-08), 프레임워크=Hypothesis(PBT-09, 기존 의존성).
- **다유형 과거 재현 코퍼스**: 서로 다른 전파 유형을 담은 **5~8개 고정 픽스처 시나리오**를 결정적으로 재현 — 각 시나리오는 과거 가격/뉴스 입력 + 기대 출력(무버 경보 + 피어 read-through 후보)으로 구성. 유형 예:
  1. **실적 쇼크 전파**(AVGO류): 실적 미스 → 반도체/AI-capex 피어 경고가 떠야 함
  2. **섹터 동반락**: 한 섹터 다수 동반 하락 → 섹터 read-through
  3. **매크로 쇼크**: 금리/유가 급변 → 해당 민감군
  4. **개별 악재 비전파**: 한 종목만의 특이 악재 → 피어 경고가 **안** 떠야 함(오탐 0 검증)
  5. **오탐0/무이벤트 날**: 임계 미달 → 아무 경보 없음
  (정확한 종목/날짜 세트는 Functional Design에서 확정)
  - 진양성(잘 올리는가)과 오탐(안 떠야 할 때 안 뜨는가)을 **둘 다** 커버.

### Tier 2 — 온디맨드 / 토큰 듦 (수동 1회, **자동·CI 미포함**)
- **에이전트 판단 평가 하니스**(FR-5a): 운영자가 명시적으로 1회 트리거. 과거 시나리오의 시그널 브리프를 실제 에이전트에 주고, 받은 read-through/무버 경고에 대한 에이전트의 판단·근거를 출력.
- 자동 스위트에서 **구조적으로 차단**(NFR-7) — 토큰 비용이 CI/반복 실행에 새어들지 않도록.
- (선택) Tier 1 보조로 라이브 페이퍼 스모크 1회(yfinance/Alpaca/Finnhub 실호출 → 출력 형태 확인).

## 범위 밖 (후속 트랙 후보)
- D: 애프터아워스/프리마켓 가격 바 캡처(일봉 사각지대 보완) — 별도 인프라 트랙
- E: 감성 모델 고도화 / 뉴스 소스 전면 다변화
- 동적 상관관계 기반 피어 자동 도출(Q3-B) — 정적 맵 운영 후 필요 시

## 핵심 요구사항 요약
리서치 턴이 "시장에서 방금 터진 큰 사건과 그 반응이 (안 보던 종목 포함) 다른 종목에 미치는 영향"을 **선제적으로 보게** 만든다: ① 무버 스캔(B)으로 큰 변동을 추리고, ② 정적 피어 맵+LLM(A)으로 read-through 경고를 띄우고, ③ 실적 캘린더(C)로 임박 catalyst를 미리 노출한다. 뉴스는 Alpaca(Benzinga)로 품질을 올리고, 실적 캘린더는 Finnhub 무료로 채운다. 모두 push + 툴 양방향으로, fail-honest·타임아웃 바운드로 안전하게.
