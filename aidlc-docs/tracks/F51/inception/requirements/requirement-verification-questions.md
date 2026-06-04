# F51 장초반 시그널 기록 및 분석 — 요구사항 확인 질문

현재 autostock에는 다음 관련 시스템이 있습니다:
- `src/surge/` — F47에서 구축 중인 EOD 급등주 감지/기록/에이전트 분석 시스템 (JSONL 기반, `steering/watch_surge/`)
- `src/agent/intraday/` — F3에서 구축한 intraday brief/wake/watch/abnormal 감지 시스템
- `src/data/intraday_*.py` — F1에서 구축한 intraday 피처 추출/수집/분석 파이프라인 (CSV 기반)
- `src/agent/journal.py` — 에이전트 의사결정 저널링
- `config/settings.yaml` → `trading.symbols` — 현재 유니버스 (약 100여개 종목)

F47의 surge detection과 유사한 방식으로, 장초반(정규장 오픈 직후) 시그널을 기록·분석하는 기능을 설계하기 위해 아래 질문에 답변해주세요.

---

## Question 1
"장초반"의 시간 범위를 어떻게 정의할까요?

A) 오픈 직후 5분 (09:30–09:35 ET)
B) 오픈 직후 15분 (09:30–09:45 ET)
C) 오픈 직후 30분 (09:30–10:00 ET)
D) 오픈 직후 1시간 (09:30–10:30 ET)
X) 기타 (Answer 태그 뒤에 설명)

[Answer]: D

---

## Question 2
어떤 종류의 "시그널"을 감지하고 기록할까요? (복수 선택이면 Answer에 여러 문자를 적어주세요)

A) 갭(gap) — 시가가 전일 종가 대비 ±X% 이상 벌어진 종목
B) 초반 급등/폭락 — 장초반 N분 내에 ±Y% 이상 움직인 종목 (갭과 별개로 오픈 후 움직임)
C) 변동성 폭발 — 장초반 범위(고가-저가)가 최근 평균 대비 Z배 이상인 종목
D) 거래량 급증 — 장초반 거래량이 평소 동시간대 대비 W배 이상
E) F47 유사 패턴 — 당일 종가 기준 급등/폭락을 장초반 데이터로 조기 감지 (EOD가 아닌 실시간)
X) 기타 (Answer 태그 뒤에 설명)

[Answer]: B. 내가 찾고싶은건 급락하면 다시 말올 하는 경우가 꽤나 많고 이런 걸 캐치하기 위한 데이터 수집이 필요해.

---

## Question 3
감지된 장초반 시그널 데이터를 어디에 어떤 형식으로 저장할까요?

A) `steering/watch_early_session/YYYY-MM-DD.jsonl` — F47과 동일한 패턴 (steering 채널 내 jsonl)
B) `data/early_session/` — F1 intraday 피처 저장소 패턴 (CSV 기반)
C) `workspace/early_session_signals.jsonl` — 에이전트 저널과 동일한 append-only 라인 기반
D) 인메모리 only — 장중에만 사용하고 EOD에 집계하여 별도 저장
X) 기타 (Answer 태그 뒤에 설명)

[Answer]: C. workspace 내 저장소 (F47 worktree를 보면 현재 workspace로 옮김)

---

## Question 4
기록된 시그널에 대해 어떤 분석을 수행할까요?

A) 통계 분석 — 장초반 시그널의 발생 빈도, 정확도(실제 당일 급등/폭락으로 이어졌는지), 패턴 안정성 통계 (F1의 Hypothesis 분석 유사)
B) Agent 분석 — EOD 리뷰 시점에 agent가 장초반 시그널 리스트를 받아 원인 분석 (F47 방식)
C) A + B 병행 — 1차 통계 필터링 → 유의미한 건만 agent 분석
D) 단순 기록 우선 — 지금은 감지+기록만 정확히 하고, 분석은 추후 고도화 (F1 P0 접근법)
X) 기타 (Answer 태그 뒤에 설명)

[Answer]:  D.

---

## Question 5
이 기능의 실행 시점은 어떻게 할까요?

A) 장중 실시간 — 장초반 시간대(예: 09:30–10:00)에 라이브로 감지하여 즉시 기록
B) EOD 분석 — 장 마감 후当日 장초반 데이터를 돌아보며 감지·분석 (F47 방식)
C) A + B 병행 — 장중 실시간 감지(즉시 기록) + EOD 최종 분석
D) Near-realtime — 오픈 후 30분~1시간 뒤에 당일 장초반 구간을 한 번에 분석
X) 기타 (Answer 태그 뒤에 설명)

[Answer]: A

---

## Question 6
이 기능은 기존 시스템과 어떻게 통합할까요?

A) F47 `src/surge/` 모듈 확장 — 기존 surge detection 시스템에 early-session 하위 기능으로 추가
B) 독립 모듈 — `src/early_session/` 또는 `src/session_open/` 등 완전히 새 모듈로 구축
C) F3 intraday 시스템 연장 — `src/agent/intraday/`에 early-session wake/abnormal 조건 추가
D) F1 intraday 피처 시스템 통합 — `src/data/` 아래 early-session 피처로 추가하여 CSV 분석 파이프라인에 편입
X) 기타 (Answer 태그 뒤에 설명)

[Answer]: B (F47과 같은 격의 독립 모듈)

---

## Question 7
Extension 설정에 관한 질문입니다.

### Question 7-1: Security Baseline
보안 규칙을 이 트랙에 적용할까요?

A) Yes — 모든 SECURITY 규칙을 차단 제약조건으로 적용 (운영 등급 애플리케이션에 권장)
B) No — 모든 SECURITY 규칙 건너뛰기 (PoC/실험적 기능에 적합)
X) 기타

[Answer]:  B

### Question 7-2: Property-Based Testing
Property-Based Testing(PBT) 규칙을 이 트랙에 적용할까요?

A) Yes — 모든 PBT 규칙을 차단 제약조건으로 적용 (비즈니스 로직, 데이터 변환에 권장)
B) Partial — 순수 함수와 serialization round-trip에만 PBT 적용 (제한된 알고리즘 복잡도에 적합)
C) No — PBT 규칙 건너뛰기 (단순 CRUD/UI 중심 작업에 적합)
X) 기타

[Answer]: B

---
