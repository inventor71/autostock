# Multi-Agent Research 교차검증 + 시그널 확장 — 요건 분석 질문

아래 질문에 답변해 주세요. 각 질문 아래의 `[Answer]:` 태그 뒤에 선택지를 기입하세요.
맞는 옵션이 없으면 `X) 기타`를 선택하고 설명을 추가하세요.

---

## 의도 분석 (Intent Analysis)

현재 research turn은 단일 `claude -p` 세션이 6단계 태스크(account truth → regime → positions → discovery → watchlist → decisions)를 한 번에 수행합니다.

사용자 요청의 두 축:
1. **교차검증**: N개 agent가 서로 교차검증하는 식으로 판단 품질 향상
2. **시그널 확장**: research turn에서 참고할 데이터 소스를 추가

참고한 오픈소스:
- **TradingAgents** (TauricResearch): Analyst 4명 → Bull/Bear 토론 → Research Manager → Trader → Risk Debate → Portfolio Manager
- **AI-Trader** (HKUDS): 에이전트 마켓플레이스 / 소셜 검증 (우리 유스케이스와 거리 있음)

---

## Question 1
**멀티에이전트 구현 방식**: N개 agent를 어떻게 구현할지 결정이 필요합니다.

A) **별도 LLM 세션 N개** — 각 agent가 독립된 `claude -p` 세션으로 실행 (병렬 가능). 각 세션은 자기 역할의 분석만 수행하고, 마지막 Synthesis 세션이 모든 보고서를 종합. 비용 = N× 현재 비용이지만 정밀도 최대화.
B) **단일 세션 내 구조화 프롬프트** — 하나의 `claude -p` 세션에서 "이제 Technical Analyst 역할로 분석하라" → "이제 Bear Researcher로 반론하라" → "종합하라" 식으로 역할을 시퀀셜하게 전환. 비용 = 1× (세션 길어짐). TradingAgents 논문이 이 방식에 가까움.
C) **하이브리드** — Analyst 분석은 별도 세션 N개로 병렬 수행(데이터 수집+분석), 토론/종합은 단일 세션에서 모든 분석 보고서를 입력받아 수행. 비용 = N+1 세션.
X) 기타 (아래 설명)

[Answer]: B+C. 둘다 구현하고 둘 중 선택하고 N도 결정할 수 있도록 함. 아래와 같이 N 세션이 주어졌을때 행동 정의 => B: N-1번의 시퀀셜 토론 (Q-2의 도구는 모두 열람 가능) + Manager 판정. C: (N-1)-sub agent launcher + Manager 판정 (병렬 수정을 할때는 각각 다른 일로 분업할 수 있도록 Manager가 N-1개의 subagent한테 일을 구분해서 launch 후 종합. Q-2 도구 모두 열람 가능, but prompt를 구분해서 일을 줌) Q-9의 multi_agent.enabled=true이면 N >=2만 가능하도록 강제 
---

## Question 2
**Agent 역할 구성**: 어떤 전문 역할을 두고 싶은지 선택해 주세요 (복수 선택 가능, 예: A,B,C).

A) **Technical Analyst** — 가격/볼륨/모멘텀/차트 패턴 분석 (현재 tools의 indicators/quote 활용)
B) **Fundamental Analyst** — 재무제표, 밸류에이션, 성장성, 배당 (현재 tools의 fundamentals 활용 + 확장)
C) **News/Sentiment Analyst** — 뉴스 분석, 소셜미디어 감성, 내부자 거래 (현재 news + 확장 시그널)
D) **Macro/Regime Analyst** — 시장 레짐, 섹터 로테이션, 금리/VIX/매크로 지표 (현재 regime.md 분석 확장)
E) **Bull/Bear Debater** — 위 분석을 받아 낙관/비관 양측에서 논쟁 후 종합 (TradingAgents 핵심 패턴)
X) 기타 (아래 설명)

[Answer]: Q-1에 따라 구성. 정보는 A,B,C,D를 모두 살펴볼 수 있도록 확장. 다만, 특정 전문역할을 두기보다는 general하게 시작해서 필요 지표를 확인할 수 있는 가이드를 주도록 하자. 여기서 궁금한 점이 있음: retrospect (자기반성)이 지금 기록되고 있을 텐데, 이거는 어떻게 설계할지를 추가 질문세션을 구성해주길 바람

---

## Question 3
**교차검증 메커니즘**: 여러 agent의 출력을 어떻게 교차검증/종합할지 결정이 필요합니다.

A) **Bull/Bear 토론 + Manager 판정** — TradingAgents 방식. Analyst 보고서를 받은 후 Bull/Bear가 K라운드 토론, Research Manager가 최종 판정. 구조화되고 검증됨, 비용 높음.
B) **독립 분석 + 투표/가중 평균** — 각 agent가 독립적으로 신호(BUY/SELL/HOLD + confidence)를 내고, 가중 평균이나 다수결로 최종 결정. 단순하고 병렬화 쉬움, 토론의 깊이 부족.
C) **독립 분석 + Synthesizer 세션** — 각 agent의 보고서를 모아 별도 Synthesizer 세션이 종합적으로 판단. 토론 없이도 다각도 고려 가능, 중간 비용.
D) **독립 분석 + 불일치 시에만 토론** — 다수 agent가 같은 방향이면 바로 결정, 의견이 나뉘면 토론 라운드 시작. 비용 효율적이면서 중요한 경우에만 깊은 분석.
X) 기타 (아래 설명)

[Answer]: A + C (Q-1과 겹침. 더 내용이 필요하면 추가 질문 세션 바람)

---

## Question 4
**기본 Agent 수 (N)과 설정 범위**: configurable한 N의 기본값과 범위를 정하고 싶습니다.

A) **N=3 기본 (2~5 범위)** — Technical + Fundamental + News/Macro. 경량화된 구성. Bull/Bear는 별도 옵션.
B) **N=4 기본 (2~6 범위)** — TradingAgents 기본과 동일. Technical + Fundamental + News + Macro 각각 분리.
C) **N=5 기본 (3~8 범위)** — 4개 Analyst + Bull/Bear 토론 포함. 완전한 TradingAgents 파이프라인.
X) 기타 (아래 설명)

[Answer]: X. N=3 기본. 범위는 [1,5]

---

## Question 5
**추가 시그널/데이터 소스**: research turn에 새로 추가할 시그널을 선택해 주세요 (복수 선택 가능, 예: A,B,C).

현재 사용 중: quote, indicators (RSI/MACD/Bollinger/SMA/volatility/ATR), fundamentals (P/E/margins/growth/beta/analyst target), news (yfinance 8건), scoreboard, WebSearch/WebFetch.

A) **옵션 플로우 (Options Flow)** — 비정상적 옵션 거래량, put/call ratio, 대량 옵션 거래 감지. 스마트 머니 신호.
B) **소셜 감성 (Social Sentiment)** — Reddit (r/wallstreetbets 등), StockTwits 감성 분석. 리테일 심리 파악.
C) **내부자 거래 (Insider Trading)** — SEC Form 4 기반 내부자 매수/매도 동향.
D) **어닝스 캘린더 + 이벤트** — 실적 발표 일정, 배당 ex-date, 스플릿 일정 등 이벤트 캘린더.
E) **확장된 매크로 지표** — Treasury yields (2Y/10Y/spread), Dollar Index, commodity prices, Fed funds futures.
X) 기타 (아래 설명)

[Answer]: X. 이거 추가 질문세션 만들어줘. 내가 주식 전문이 아니라서. LLM이 쉽게 분석가능할정도로 파싱될만한 옵션이 뭐가 있고, 유의미함을 글로서 파악 할 수 있는게 뭐가 있을까

---

## Question 6
**비용/지연 허용 범위**: N개 agent = N× LLM 비용 + 추가 시그널 API 비용. 어느 수준까지 허용하시겠습니까?

A) **비용 무관, 품질 최우선** — research turn이 하루 1회이므로 비용보다 판단 품질이 중요. 시간 제한도 느슨하게 (예: research timeout 3600s+).
B) **합리적 증가 (2~3× 현재 비용)** — 핵심 역할만 별도 세션으로, 나머지는 구조화 프롬프트로. 시간 제한 현재 수준(1800s) 유지하되 필요시 확장.
C) **최소 비용 증가 (1.5× 이내)** — 단일 세션 + 구조화 프롬프트 위주. 추가 시그널 API는 무료 소스만.
X) 기타 (아래 설명)

[Answer]: B.

---

## Question 7
**Reflection/학습 메커니즘**: TradingAgents는 실행 후 실제 수익률을 벤치마크와 비교해 반성문을 생성하고, 다음 research turn에 주입합니다. 현재 EOD review (review.py)가 있지만 다음 날 research에 피드백하지는 않습니다.

A) **도입** — EOD/트레이드 종료 시 반성문 생성 → `lessons.md` 또는 별도 파일에 저장 → 다음 research turn에 최근 N개 반성 주입. 판단 품질 점진적 개선 기대.
B) **보류** — 현재 EOD review + lessons.md 구조 그대로 유지. 멀티에이전트 교차검증이 우선, 학습 루프는 나중에.
X) 기타 (아래 설명)

[Answer]: A.

---

## Question 8
**구조화된 출력**: 각 agent의 분석 결과를 자유 텍스트로 둘지, Pydantic-like 구조화된 스키마로 강제할지.

A) **구조화된 출력 강제** — 각 Analyst 보고서를 JSON/구조화 형식으로 (예: `{recommendation, confidence, key_signals, risks}`). 파싱 안정적, 자동 합산/투표 가능.
B) **자유 텍스트 + 구조화 결론** — 본문은 자유 텍스트(심층 분석), 마지막에 구조화된 결론 섹션만 강제 (예: `## Verdict: BUY 0.75`).
C) **완전 자유 텍스트** — 각 agent가 자유롭게 분석. Synthesizer가 모든 텍스트를 읽고 종합. 가장 유연하지만 파싱 불안정.
X) 기타 (아래 설명)

[Answer]: B. 구조화된 결론 섹션은 F22로 개발되고 있는 AI 탑바에서 research turn에 대한 정보로 사용가능하도록 함.

---

## Question 9
**기존 research turn과의 관계**: 멀티에이전트 도입 시 기존 6단계 research turn 구조를 어떻게 할지.

A) **완전 대체** — 기존 단일 research turn을 멀티에이전트 파이프라인으로 교체. 설정으로 `multi_agent.enabled=true/false`로 토글. false이면 기존 방식.
B) **병행 (A/B 테스트)** — 기존 방식과 멀티에이전트 방식 모두 실행, 일정 기간 결과 비교 후 전환.
C) **점진적 확장** — 기존 research turn 구조를 유지하되, 각 단계에서 교차검증 레이어만 추가 (예: regime 분석 시 2nd opinion 주입).
X) 기타 (아래 설명)

[Answer]: A

---

## Question 10
**Worktree + 브랜치 전략**: 이 작업은 어떤 방식으로 분리할지.

A) **새 worktree + feat/F23 브랜치** — 기존 관행대로 독립 worktree에서 작업. main에 머지.
B) **기존 F22와 병합** — F22 (AI 협업 TUI 개선)와 관련성이 높으므로 같은 트랙에서 진행.
X) 기타 (아래 설명)

[Answer]: A.

---

## Question 11: Security Extensions
이 트랙에 보안 확장 규칙을 적용할까요?

A) 적용 — 모든 SECURITY 규칙을 blocking constraint로 적용 (프로덕션 수준 권장)
B) 미적용 — SECURITY 규칙 생략 (PoC/프로토타입/실험적 프로젝트)
X) 기타 (아래 설명)

[Answer]: A

---

## Question 12: Property-Based Testing Extension
이 트랙에 Property-Based Testing(PBT) 규칙을 적용할까요?

A) 전체 적용 — 모든 PBT 규칙을 blocking constraint로 적용
B) 부분 적용 — pure function과 직렬화 round-trip에만 PBT 적용 (이 프로젝트의 기본 모드)
C) 미적용 — PBT 규칙 생략
X) 기타 (아래 설명)

[Answer]: B

---
