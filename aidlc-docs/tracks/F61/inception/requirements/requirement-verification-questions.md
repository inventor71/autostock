# F61 요구사항 확인 질문 (리서치 턴 주식 시그널 강화)

> 각 질문의 `[Answer]:` 태그 뒤에 답을 적어주세요. 객관식은 A/B/C/... 중 선택, 없으면 X) Other에 자유 기술.
> 진단(직전 대화)에서 확인된 공백을 전제로 합니다. **범위 확정(Q1)이 가장 중요**합니다.

---

## 배경 (진단 요약)
브로드컴(AVGO) 실적 폭락을 autostock이 캐치하지 못함. 코드 분석 결과 5대 공백:
1. 뉴스 = 종목별 pull + 에이전트 직접 호출 → 시장 전체 catalyst surfacing 없음
2. 뉴스 소스 단일(yfinance) + 제목 키워드 감성 휴리스틱
3. 전부 일봉 기반 → 애프터아워스/실적 갭 사각지대
4. surge 감지기 = EOD·유니버스 한정·일봉·사후 기록 (선제 전파 없음)
5. **종목 간 전파(read-through/contagion) 모델링 전무** ← 사용자가 지목한 핵심
   (+ 실적 캘린더 awareness 부재)

---

## Q1. 이번 트랙의 범위 — 어느 공백을 다룰까요? (가장 중요)
한 트랙에 다 넣으면 비대해집니다. 우선순위를 정해주세요. (복수 선택 가능)

A) **종목 간 read-through 전파만** — 큰 변동(예: AVGO↓)을 섹터/연관 피어로 연결해 리서치 턴에 경고로 surfacing (핵심 공백 집중, 가장 작은 단위)
B) **시장 전체 무버/catalyst 스캔 추가** — 유니버스 daily change·volume·신규 뉴스를 리서치 턴 앞단에 push (pull→push)
C) **실적 캘린더 surfacing** — 임박 실적을 리서치 턴에 사전 노출 + 보유종목 read-through 점검 유도
D) **애프터아워스/프리마켓 가격 캡처** — 일봉 사각지대 보완 (실적 갭 포착)
E) **뉴스 소스/감성 업그레이드** — yfinance 단일 의존 탈피 + 키워드 휴리스틱 대체
F) **A+B+C 묶음** (전파 + 무버 스캔 + 실적 캘린더 — "리서치 턴이 시장에서 방금 터진 일을 먼저 본다"는 하나의 일관된 묶음, D/E는 후속 트랙)
X) Other

[Answer]: 

---

## Q2. 데이터 소스 범위 — 새 비용/의존성을 추가해도 되나요?
현재는 yfinance 단일. 무버/뉴스/AH 데이터는 소스에 따라 비용·복잡도가 다릅니다.

A) **yfinance 안에서 최대한 해결** — 추가 의존성/비용 없이 (속도·커버리지 한계 감수)
B) **이미 연동된 Alpaca 데이터 활용 추가** — Alpaca의 뉴스/실시간·AH 바를 사용 (이미 키 있음, 추가 비용 적음)
C) **신규 외부 소스/유료 API 허용** — 더 빠르고 정확한 뉴스/무버 (비용·키 관리 발생)
X) Other

[Answer]: 

---

## Q3. read-through(전파) 메커니즘의 정교함 — 어느 수준?
(Q1에서 A 또는 F를 고른 경우에만 해당)

A) **정적 피어 맵** — 종목→섹터/연관군 사전 정의 테이블 (예: AVGO→반도체:NVDA,AMD,... / AI-capex). 단순·결정적·설명 가능
B) **동적 상관관계 계산** — 가격 히스토리에서 상관/베타를 계산해 피어 자동 도출 (데이터 기반, 무겁고 노이즈)
C) **LLM 추론 위임** — Python은 "큰 변동 발생" 사실만 push하고, 어느 종목에 read-through되는지는 에이전트가 판단 (유연하나 결정론 약함)
D) **A + C 하이브리드** — 정적 피어 맵으로 후보를 좁혀 push하고, 최종 판단은 에이전트 (추천: 결정성 + 유연성)
X) Other

[Answer]: 

---

## Q4. 새 시그널을 리서치 턴에 어떻게 노출할까요?
현재 시그널 툴은 에이전트가 `python -m src.agent.tools <name>`로 직접 호출하는 pull 구조.

A) **새 on-demand 툴만 추가** — 에이전트가 필요 시 호출 (`tools movers` / `tools readthrough <SYM>` 등). 기존 패턴과 일관, 하지만 "안 부르면 못 봄"
B) **리서치 프롬프트 앞단에 자동 push** — Python이 무버/전파 경보를 조립해 morning_research_prompt에 prepend (에이전트가 반드시 보게 됨)
C) **A+B 둘 다** — push로 주의를 끌고, 깊이 파는 건 툴로 (추천)
X) Other

[Answer]: 

---

## Q5. 스캔 대상 유니버스 범위 — bellwether를 유니버스 밖까지 볼까요?
AVGO는 사실 유니버스 안에 있었습니다. 하지만 유니버스 밖 대형 bellwether(예: 지수 ETF, 미편입 대장주)가 시장을 흔드는 경우도 있습니다.

A) **유니버스 내로 한정** — 거래 가능 종목만 (단순, 거래로 직결)
B) **유니버스 + 소수 bellwether 워치리스트** — 거래는 안 하지만 시그널 소스로 보는 추가 종목 허용 (예: SPY/QQQ/SMH 등 ETF, 미편입 대장주)
X) Other

[Answer]: 

---

## Q6. 검증(verification) 기준 — 이 기능이 "동작한다"를 어떻게 확인할까요?
시그널 기능은 시장 상황 의존적이라 라이브 검증이 어렵습니다.

A) **유닛 테스트 중심** — 합성 데이터로 전파/무버 로직의 결정성 검증 (네트워크 불요, 빠름)
B) **유닛 + 과거 사례 재현** — AVGO 폭락일 같은 과거 데이터로 "그날이면 경보가 떴을까" 재현 테스트
C) **유닛 + 라이브 페이퍼 스모크** — 실제 yfinance/Alpaca로 1회 실행해 출력 확인 (worktree live verification)
X) Other

[Answer]: 

---

## Q7. (확장) 보안 베이스라인 — 이 트랙에 강제할까요?
## Question: Security Extensions
Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)
B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)
X) Other (please describe after [Answer]: tag below)

[Answer]: 

---

## Q8. (확장) 속성 기반 테스트(PBT) — 이 트랙에 강제할까요?
## Question: Property-Based Testing Extension
Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic, data transformations, serialization, or stateful components)
B) Partial — enforce PBT rules only for pure functions and serialization round-trips (suitable for projects with limited algorithmic complexity)
C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or thin integration layers with no significant business logic)
X) Other (please describe after [Answer]: tag below)

[Answer]: 
