# F47 급등주 히스토리 기록 및 원인 분석 — 요구사항 확인 질문

현재 autostock에는 다음 관련 시스템이 있습니다:
- `src/data/intraday_*.py` — F1에서 구축한 intraday 피처 추출/수집/분석 파이프라인 (CSV 기반, yfinance/Alpaca 백필)
- `src/agent/intraday/` — F3에서 구축한 intraday brief/wake/watch/abnormal 감지 시스템
- `src/agent/journal.py` — 에이전트 의사결정 저널링 (decisions.jsonl, turns.jsonl)
- `src/agent/review.py` — EOD 리뷰 (outcome_lines, daily_summary)
- `config/settings.yaml` → `trading.symbols` — 현재 유니버스 (약 100여개 종목)

아래 질문에 답변해주세요.

---

## Question 1
급등주(急騰株)의 기준을 어떻게 정의할까요? (복수 선택 가능하면 Q1-A에서 임계값을, Q1-B에서 시간窗口를 선택)

A) 일간 등락률 기준 — 전일 종가 대비 당일 종가 ±X% 이상 (예: +5%, +10%)
B) 장중 최고가 기준 — 당일 고가가 전일 종가 대비 ±X% 이상
C) 거래량 동반 — 가격 급등 + 평소 대비 거래량 N배 이상
D) 복합 조건 — A+B+C 중 2개 이상 충족
X) 기타 (Answer 태그 뒤에 설명)

[Answer]: A

---

## Question 2
급등 원인 분석의 깊이는 어느 정도로 할까요?

A) 자동 분류 — 감지된 급등주에 대해 미리 정의된 카테고리(예: 실적발표, 뉴스, 섹터 동반 상승, 기술적 돌파, 알 수 없음)로 자동 태깅
B) Agent 분석 — EOD 리뷰 시점에 agent가 급등주 리스트를 받아 뉴스/재료를 검색하고 자연어 분석을 추가
C) 하이브리드 — 자동 분류 1차 패스 → 분류 불가/불확실한 건만 agent에게 전달
D) 단순 기록 우선 — 지금은 급등 감지만 정확히 기록하고, 원인 분석은 정보 갭만 태깅 (추후 고도화)
X) 기타

[Answer]: B

---

## Question 3
"현 autostock에서 주는 정보만으로는 설명이 안 되는 급등"의 정보 갭(information gap)을 어떻게 구조화할까요?

A) 사전 정의된 갭 카테고리 — 뉴스/공시, 섹터/테마, 수급/기관매매, 글로벌 매크로, 시간외 재료, 기타 중 선택
B) 자유 텍스트 — agent가 자연어로 갭을 설명하고, 주기적으로 리뷰하여 패턴 파악
C) 구조화된 갭 레코드 — {symbol, date, surge_pct, suspected_cause: enum|null, missing_data_source: str, priority: low|med|high} 형태의 정형 데이터
D) A + C 조합 — 카테고리 + 정형 레코드
X) 기타

[Answer]: B. 분석에 용이한 구조를 이번 FR에서 만들어나간다고 생각함.

---

## Question 4
급등주 히스토리는 어디에 어떤 형식으로 저장할까요?

A) CSV 파일 — `data/surge_history/YYYY-MM-DD.csv` (기존 intraday_store.csv 패턴과 유사)
B) JSONL 파일 — `workspace/surge_history.jsonl` (에이전트 저널과 동일한 append-only 라인 기반)
C) 새로운 전용 디렉토리 — `data/surge_history/{symbol}/` 아래 일자별 기록
D) 인메모리 + EOD 덤프 — 장중 실시간 감지 → EOD에 파일로 기록
X) 기타

[Answer]: X. steer 안에 watch_surge/ 디렉토리 내부에 jsonl

---

## Question 5
급등 감지는 언제 실행할까요?

A) EOD 단일 실행 — 장 마감 후当日 전체 유니버스 스캔, 급등주 리스트 + 원인 분석 수행
B) 장중 주기적 폴링 — 5~15분 간격으로 스캔, 급등 감지 즉시 기록 (실시간성)
C) A + B 병행 — 장중 실시간 감지(알림 목적) + EOD 최종 집계 및 원인 분석
D) EOD + 필요시 on-demand — 기본은 EOD, `/surge-check` 명령으로 수동 실행 가능
X) 기타

[Answer]: A

---

## Question 6
이 기능은 기존 intraday 시스템(F1/F3)의 연장선에서 구현할까요, 아니면 완전히 독립적인 새 모듈로 만들까요?

A) F1/F3 연장 — 기존 `src/data/intraday_*.py` + `src/agent/intraday/`에 surge 관련 모듈 추가, 동일한 데이터 파이프라인 공유
B) 독립 모듈 — `src/surge/` 또는 `src/data/surge/`에 완전히 새로 구축, intraday 시스템과 분리
C) 데이터만 공유 — intraday 가격 데이터는 재사용하되, 분석 로직은 별도 모듈로 분리
X) 기타

[Answer]: B. 어차피 급등했는지 안했는지 일별 정보만 하루에 한번 필요.

---

## Question 7
Extension 설정에 관한 질문입니다.

### Question 7-1: Security Baseline
보안 규칙을 이 트랙에 적용할까요?

A) Yes — 모든 SECURITY 규칙을 차단 제약조건으로 적용 (운영 등급 애플리케이션에 권장)
B) No — 모든 SECURITY 규칙 건너뛰기 (PoC/실험적 기능에 적합)
X) 기타

[Answer]: B

### Question 7-2: Property-Based Testing
Property-Based Testing(PBT) 규칙을 이 트랙에 적용할까요?

A) Yes — 모든 PBT 규칙을 차단 제약조건으로 적용 (비즈니스 로직, 데이터 변환에 권장)
B) Partial — 순수 함수와 serialization round-trip에만 PBT 적용 (제한된 알고리즘 복잡도에 적합)
C) No — PBT 규칙 건너뛰기 (단순 CRUD/UI 중심 작업에 적합)
X) 기타

[Answer]: B

---
