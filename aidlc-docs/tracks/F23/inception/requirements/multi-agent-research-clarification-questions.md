# Multi-Agent Research — 추가 질문 세션

Q2(retrospect 설계)와 Q5(시그널 확장)에 대한 추가 질문입니다.
`[Answer]:` 태그 뒤에 선택지를 기입해 주세요.

---

## Part A: Retrospect(자기반성) 설계 — Q2 / Q7 후속

### 현재 상태 요약

이미 닫힌 학습 루프가 동작 중입니다:
1. **EOD review turn** → broker truth (실제 가격/포지션/P&L) 기반 outcome snapshot 생성
2. **에이전트가 기록**: `positions/<SYM>.md`에 Call-vs-Outcome 테이블 + `lessons.md`에 일반화된 교훈 추가
3. **다음 날 research turn** → `lessons.md`를 읽고 의사결정에 인용 (실제 확인됨: "lesson #1/#5" 인용하며 RSI>75 종목 매수 거부)

`lessons.md`에는 현재 7개의 curated lesson이 있고, `daily/<date>.md`에는 자기 채점 (regime read, discovery, discipline 등)이 기록됩니다.

---

### CQ-1: 멀티에이전트에서의 retrospect 귀속
멀티에이전트 구조에서 retrospect를 누가 수행할지 결정이 필요합니다.

A) **Manager(종합) 세션만 retrospect 수행** — 최종 결정을 내린 Manager가 EOD review에서 자기반성을 작성하고, 다음 날 research turn의 모든 agent에게 lessons.md를 주입. 일관된 단일 학습 루프.
B) **각 sub-agent도 개별 retrospect** — 각 분석 agent가 자기 분석의 정확도를 EOD에 평가 (예: Technical Analyst: "RSI 과매수 경고를 냈는데 실제로 반전했나?"). Manager는 전체 종합 retrospect. 더 세밀한 피드백이지만 비용 증가.
C) **현재 방식 유지 + Manager에게 주입** — 기존 단일 세션 EOD review(=현재 코드) 그대로 유지. 다음 날 멀티에이전트 research에서는 Manager 세션에만 lessons.md를 주입. Sub-agent에게는 주입하지 않음 (역할 범위를 분석에 한정).
X) 기타 (아래 설명)

[Answer]: 

---

### CQ-2: 반성문의 구조화 수준
현재 `lessons.md`는 자유 텍스트 bullet point (`- [2026-05-27] Don't chase overbought names...`). 멀티에이전트에서 반성의 구조를 강화할지.

A) **현재 형식 유지** — 자유 텍스트 bullet. LLM이 자연어로 읽기 좋고, 에이전트가 자기 스타일로 교훈을 표현. 검증됨 (이미 작동 중).
B) **구조화된 retrospect 레코드** — 각 교훈을 `{lesson_id, date, category, signal_used, outcome, takeaway, times_applied}` 형태로 저장. 적용 횟수 추적, 카테고리별 필터 가능. 관리 오버헤드 증가.
C) **하이브리드** — `lessons.md`는 현재 방식 유지 (에이전트가 읽는 용도), 별도 `lessons.jsonl`에 구조화 레코드 저장 (분석/대시보드 용도). 이중 관리이지만 양쪽 장점.
X) 기타 (아래 설명)

[Answer]: 

---

### CQ-3: Reflection 주기와 대상
Q7에서 도입 결정. 반성의 주기와 대상 범위를 정합니다.

A) **EOD 매일 + 포지션 종료 시** — 매 거래일 마감 시 전체 반성 + 포지션이 stop/target/manual로 종료될 때마다 해당 트레이드의 post-mortem. 현재 EOD review를 확장하는 형태.
B) **EOD 매일만** — 현재와 동일 주기. 포지션별 post-mortem은 EOD review 내에서 자연스럽게 발생 (이미 Call-vs-Outcome 기록).
C) **주간 종합 + EOD 매일** — 금요일(또는 주 마지막 거래일)에 주간 종합 retrospect를 추가. 단기 lessons과 중기 패턴을 분리.
X) 기타 (아래 설명)

[Answer]: 

---

## Part B: 시그널 확장 — Q5 후속

### 조사 결과 요약

LLM이 텍스트로 파싱/해석 가능하고, 무료 API로 즉시 구현 가능한 시그널을 조사했습니다. 모든 1순위 항목은 **yfinance만으로 구현 가능** (추가 의존성 제로):

| 시그널 | 소스 | 구현 시간 | LLM 파서빌리티 | 시그널 가치 | 비고 |
|--------|------|----------|---------------|------------|------|
| **어닝스 캘린더** | yfinance `calendar`/`earnings_dates` | 20분 | 5/5 | 5/5 | 에이전트가 어닝스 날짜 모르고 트레이딩하는 것은 치명적 블라인드스팟 |
| **내부자 거래** | yfinance `insider_transactions` | 30분 | 5/5 | 4/5 | 학술적으로 검증된 시그널, 특히 cluster buying |
| **Short Interest** | yfinance `info` (이미 로드됨) | 5분 | 4/5 | 3/5 | `_FUNDAMENTAL_KEYS`에 3개 필드 추가만으로 완료 |
| **Analyst Upgrades** | yfinance `upgrades_downgrades` | 15분 | 5/5 | 3/5 | 이미 있는 데이터를 안 쓰고 있음 |
| **매크로 지표** | yfinance `^TNX`, `DX-Y.NYB`, `GC=F` 등 | 30분 | 5/5 | 4/5 | regime.md 판단 직접 개선 |
| **10-K/10-Q 섹션** | EdgarTools (무료, 키 불필요) | 2-3시간 | 5/5 | 4/5 | LLM 차별화 핵심이지만 의존성 추가 |
| **Options Flow** | yfinance `option_chain()` | 1-2시간 | 3/5 | 3/5 | vol/OI 이상치 감지, pre-filter 필요 |
| **소셜 감성** | StockTwits API (무료) | 1시간 | 4/5 | 2/5 | 노이즈 높음, 보조 지표 |
| **기관 보유** | yfinance `institutional_holders` | 20분 | 4/5 | 2/5 | 45일 지연으로 제한적 |

---

### CQ-4: 1순위 시그널 — 즉시 추가할 항목 선택
아래에서 F23 트랙에 포함할 1순위 시그널을 선택해 주세요 (복수 선택 가능).

A) **어닝스 캘린더** — "earnings in 3 days, consensus EPS $2.15, last beat by 8.2%" 형태. 에이전트가 어닝스 전후 위험 관리 가능.
B) **내부자 거래** — "CEO bought 50K shares @ $142 ($7.1M) — largest in 2 years" 형태. SEC Form 4 기반.
C) **Short Interest 필드** — `fundamentals()` 응답에 shortRatio, shortPercentOfFloat 추가. 코드 1줄 변경.
D) **Analyst Upgrades/Downgrades** — `fundamentals()` 응답에 최근 5건 upgrade/downgrade 추가.
E) **매크로 지표 (yfinance)** — 새 `macro()` 도구: 10Y yield, Dollar Index, Gold, Oil 등 compact 대시보드.
X) 기타 (아래 설명)

[Answer]: 

---

### CQ-5: 2순위 시그널 — 이후 추가 고려할 항목
1순위 외에 2순위로 구현을 고려할 시그널을 선택해 주세요 (복수 선택 가능, 또는 "없음"으로 답변).

A) **10-K/10-Q 섹션 추출** — EdgarTools로 Risk Factors, MD&A 등 핵심 섹션 텍스트 추출. LLM이 장문 텍스트를 읽고 해석하는 것이 최대 강점이지만, 새 의존성 추가 + 컨텍스트 크기 관리 필요.
B) **Options Flow (자체 감지)** — yfinance `option_chain()`으로 vol/OI 비율 이상치 감지. 스마트머니 시그널이지만 pre-filter 로직 필요.
C) **소셜 감성 (StockTwits)** — 무료 API, bull/bear 태그 이미 포함. 리테일 심리 파악이지만 노이즈 높음.
D) **기관 보유 비율** — yfinance로 기관 보유 비율만 `fundamentals()`에 추가. 45일 지연이지만 구조적 정보로 유용.
E) **FRED 매크로 (심화)** — fredapi로 yield curve spread, Fed funds futures, CPI 등. yfinance 매크로로 부족할 때.
F) 없음 — 1순위만 우선 구현, 2순위는 보류.
X) 기타 (아래 설명)

[Answer]: 

---

### CQ-6: 시그널을 configurable하게 만드는 방식
Q1 원문에서 "모두 setting으로 configurable하면 좋겠네"라고 하셨습니다. 시그널 on/off를 어떻게 관리할지.

A) **settings.yaml에 시그널 목록** — `research.signals: [earnings, insider, macro, ...]` 형태로 각 시그널 on/off. 에이전트 프롬프트에 enabled된 시그널만 도구 가이드로 주입.
B) **모두 기본 활성화, 끄기만 가능** — 모든 시그널 기본 on. `research.disabled_signals: [social_sentiment]` 형태로 명시적 비활성화.
C) **프로필 기반** — `research.profile: balanced | aggressive | minimal`. 프로필별 시그널 조합 사전 정의. 개별 override도 가능.
X) 기타 (아래 설명)

[Answer]: 

---
