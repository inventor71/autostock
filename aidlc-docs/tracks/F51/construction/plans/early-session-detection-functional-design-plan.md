# F51 Early-Session Detection — Functional Design Plan

> **Unit**: `early-session-detection` | **Depth**: Standard | **Reference**: F47 surge-detection 패턴

## Plan Overview

Functional Design에서는 다음 artifact 3종을 생성한다:
1. `domain-entities.md` — 핵심 도메인 엔티티와 관계
2. `business-logic-model.md` — 비즈니스 로직 모델링 (버퍼, 감지, 덤프 흐름)
3. `business-rules.md` — 비즈니스 규칙, 검증, 제약조건

UI가 없으므로 `frontend-components.md`는 생략한다 (F47과 동일).

---

## 설계 질문

아래 질문에 답변 후 진행한다.

### Question 1: 감지 임계값 기본값
급등/급락 감지의 기본 임계값(X%)과 시간窗口(M분)은?

A) 5분 내 ±3% (보수적 — 많은 시그널, 노이즈 포함 가능)
B) 5분 내 ±5% (중간 — 의미 있는 움직임 위주)
C) 10분 내 ±3% (완만한 기준)
D) 10분 내 ±5% (엄격 — 큰 움직임만)
X) 기타

[Answer]: D

---

### Question 2: 덤프 구간 기본값
감지 시점 기준 전(P분) / 후(Q분) 덤프 구간의 기본값은?

A) P=10분 전, Q=30분 후 — 보수적 (오픈 1시간 내 거의 전체 커버)
B) P=15분 전, Q=30분 후 — 균형 (버퍼 15분 + 이후 30분 추적)
C) P=15분 전, Q=45분 후 — 넉넉한 후속 추적
D) P=5분 전, Q=15분 후 — 컴팩트 (급락 직전/직후 집중)
X) 기타

[Answer]: C

---

### Question 3: 동일 종목 재감지
장초반 1시간 내에 한 종목이 한 번 시그널이 발생한 후, 같은 날 추가 시그널도 감지할까?

A) 일 1회만 (idempotency — 최초 감지만 기록, 이후 무시)
B) 일단 덤프 시작 후 Q분 경과하면 재감지 허용 (완전히 별개 이벤트로)
C) 첫 감지 후 더 큰 폭의 움직임이 발생하면 새 이벤트로 추가 기록 (같은 방향이든 반대든)
X) 기타

[Answer]: A

---

### Question 4: 데이터 입도 (Granularity)
초기 구현의 데이터 입도는?

A) 1분 봉 OHLCV (Alpaca 무료 티어 호환, 구현 단순)
B) 1분 봉 + 실시간 Trade (last_price) 혼합 — 바는 OHLCV, 감지용 가격은 trade로 더 촘촘하게
C) 가능한 최고 해상도로 시작 — Alpaca 무료 티어의 tick/quotes API가 가능하면 tick부터 시도
X) 기타

[Answer]: A

---

### Question 5: Provider 확장 방식
기존 `BaseDataProvider`에 다중심볼 bars 조회를 추가하는 방식은?

A) `get_bars` 시그니처를 `symbol: str | list[str]`로 확장 (기존 호환성 유지)
B) 새 메서드 `get_bars_batch(symbols: list[str])` 추가 (명시적 분리)
C) `get_bars`를 list-only로 변경하고 단일심볼 호출부를 모두 마이그레이션
X) 기타

[Answer]: A

---

## Plan Execution

질문 답변 완료 후 아래 체크리스트 순서로 Functional Design artifact 생성:

- [x] Q1–Q5 답변 분석
- [x] `domain-entities.md` — E1 CircularBuffer, E2 BarRecord, E3 SignalDetector, E4 SignalEvent, E5 EventIndex, E6 DumpWindow, E7 DetectionConfig 작성
- [x] `business-logic-model.md` — BLM-1 EarlySessionMonitor, BLM-2 BufferManager, BLM-3 SignalDetector, BLM-4 WindowDumper, BLM-5 IndexWriter, BLM-6 Provider 확장
- [x] `business-rules.md` — BR-1~BR-11: 모니터링 시간, 폴링, 버퍼, 감지, idempotency, 덤프, 인덱스, 에러 처리, 설정, Operator 가시성, 저장소 정리 + PBT 대상 식별
