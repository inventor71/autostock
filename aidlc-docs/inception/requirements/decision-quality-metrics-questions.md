# Decision Quality Metrics — 요구사항 분석 질문

아래 질문에 답변해 주세요. 각 질문의 `[Answer]:` 태그 뒤에 선택지 문자를 입력해 주세요.
선택지가 맞지 않으면 마지막 옵션(기타)을 선택하고 설명을 적어 주세요.

---

## Question 1
데이터 입력 소스: decisions.jsonl 외에 어떤 데이터를 메트릭 계산에 사용할까요?

A) decisions.jsonl + yfinance 가격 히스토리 (브로커 연결 없이 오프라인 분석)
B) decisions.jsonl + Alpaca 브로커 히스토리 (fills/activities API) + yfinance 가격
C) decisions.jsonl + match_round_trips 결과 (src/core/trades.py) + yfinance 가격
X) 기타 (아래 [Answer]: 태그 뒤에 설명해 주세요)

[Answer]: B

## Question 2
분석 대상 기간: 메트릭은 어떤 범위의 결정을 분석할까요?

A) 전체 기간 — decisions.jsonl의 모든 결정을 한 번에 분석
B) 슬라이딩 윈도우 — 최근 N일/N건 단위로 롤링 분석 (트렌드 변화 감지)
C) 둘 다 — 전체 + 롤링 윈도우 (전체 요약 + 시간에 따른 변화)
X) 기타 (아래 [Answer]: 태그 뒤에 설명해 주세요)

[Answer]: C

## Question 3
출력 형식: 분석 결과를 어떻게 소비할까요?

A) CLI 스크립트 — `python -m src.agent.quality` 실행 → 터미널 리포트 (Rich 테이블) + JSON 저장
B) 마크다운 리포트 파일 — workspace/quality/ 아래에 날짜별 리포트 생성
C) 둘 다 — CLI 출력 + 파일 저장
X) 기타 (아래 [Answer]: 태그 뒤에 설명해 주세요)

[Answer]: A

## Question 4
통계 검증 (Vibe-Trading 스타일): Monte Carlo / Bootstrap / Walk-Forward를 v1에 포함할까요?

A) v1에 포함 — 메트릭과 통계 검증을 한 번에 빌드
B) v1은 메트릭만, 통계 검증은 후속 트랙으로 분리
X) 기타 (아래 [Answer]: 태그 뒤에 설명해 주세요)

[Answer]: X — v1에서 아예 제외. 후속 트랙도 아니고 일단 빼기.

## Question 5
MAE/MFE 계산에 필요한 가격 경로: 어떤 해상도를 사용할까요?

A) 일봉 (daily OHLC) — 단순하고 데이터 획득 용이
B) 5분봉 (intraday) — 정밀하지만 데이터 양 많음, 기존 IntradayFeatureStore 활용 가능
C) 일봉 기본, 5분봉은 선택적 고해상도 모드
X) 기타 (아래 [Answer]: 태그 뒤에 설명해 주세요)

[Answer]: A

## Question 6
벤치마크: 초과 성과 비교 대상은?

A) SPY (S&P 500 ETF) 단일 벤치마크
B) SPY + QQQ (NASDAQ) 두 가지
C) 설정 가능 — config/settings.yaml에서 벤치마크 심볼 지정
X) 기타 (아래 [Answer]: 태그 뒤에 설명해 주세요)

[Answer]: B

## Question 7
EOD 리뷰 연동: 분석 결과를 에이전트의 EOD 리뷰 턴에 주입할까요?

A) 아니오 — 독립 분석 도구로만 사용 (에이전트 프롬프트에 주입하지 않음)
B) 예 — 주간/월간 요약을 lessons.md에 자동 추가
C) 예 — EOD 리뷰 프롬프트에 최근 메트릭 스냅샷 주입
X) 기타 (아래 [Answer]: 태그 뒤에 설명해 주세요)

[Answer]: C

## Question 8: Security Extensions
이 트랙에 보안 확장 규칙을 적용할까요?

A) 예 — SECURITY 규칙을 blocking 제약으로 적용 (프로덕션 수준 권장)
B) 아니오 — SECURITY 규칙 건너뜀 (PoC/프로토타입/실험용)
X) 기타 (아래 [Answer]: 태그 뒤에 설명해 주세요)

[Answer]: A

## Question 9: Property-Based Testing Extension
이 트랙에 속성 기반 테스트(PBT) 규칙을 적용할까요?

A) 예 — 모든 PBT 규칙을 blocking 제약으로 적용
B) 부분 적용 — 순수 함수와 직렬화 왕복에만 PBT 적용 (메트릭 계산 함수에 적합)
C) 아니오 — PBT 규칙 건너뜀
X) 기타 (아래 [Answer]: 태그 뒤에 설명해 주세요)

[Answer]: B
