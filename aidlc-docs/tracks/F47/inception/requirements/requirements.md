# F47 급등주 히스토리 기록 및 원인 분석 — 요구사항

> **Depth**: Standard | **Complexity**: Moderate | **Scope**: Multiple Components

## Intent Analysis Summary

| 항목 | 내용 |
|------|------|
| **User Request** | 매일 유니버스 내 급등주를 자동 감지하여 히스토리 기록, 원인 분석, 정보 갭 식별. 장기적으로 agent 예측으로 발전 |
| **Request Type** | New Feature |
| **Scope Estimate** | Multiple Components — 데이터 감지 → agent 분석 → steering 채널 저장 |
| **Complexity** | Moderate — 독립 모듈이나 agent 통합, 데이터 모델 설계 필요 |
| **Depth** | Standard |

---

## 1. Functional Requirements

### FR-1: 급등주 감지 (Surge Detection)
- **FR-1.1**: 매일 EOD(장 마감 후)에 유니버스(`config/settings.yaml` → `trading.symbols`) 전체 종목의 당일 등락률을 계산한다.
- **FR-1.2**: 전일 종가 대비 당일 종가 등락률이 **+7% 이상**인 종목을 "급등주"로 분류한다.
- **FR-1.3**: 급등 임계값(7%)은 `config/settings.yaml`의 `surge:` 블록에서 조정 가능해야 한다 (기본값 7%).
- **FR-1.4**: 가격 데이터 조회에 실패한 종목은 스킵하고 로그를 남긴다 (fail-closed).

### FR-2: 급등주 히스토리 기록 (Surge History Recording)
- **FR-2.1**: 감지된 급등주 정보를 `steering/watch_surge/YYYY-MM-DD.jsonl` 파일에 JSONL 형식으로 기록한다.
- **FR-2.2**: 각 레코드는 다음 필드를 포함한다:
  - `symbol` — 종목 티커
  - `date` — 거래일 (YYYY-MM-DD)
  - `close_prev` — 전일 종가
  - `close_today` — 당일 종가
  - `change_pct` — 등락률 (%)
  - `volume` — 당일 거래량
  - `avg_volume_20d` — 20일 평균 거래량
  - `volume_ratio` — 거래량 비율 (당일/평균)
  - `high_today` / `low_today` — 당일 고가/저가
  - `detected_at` — 감지 시각 (ISO 8601)
- **FR-2.3**: 동일 날짜에 동일 종목이 중복 기록되지 않도록 idempotency 보장 (date + symbol 기준).

### FR-3: Agent 급등 원인 분석 (Agent Root-Cause Analysis)
- **FR-3.1**: EOD 리뷰 시점에 agent에게 급등주 리스트를 제공하고, 각 급등주에 대해 원인 분석을 요청한다.
- **FR-3.2**: Agent는 각 급등주에 대해 semi-structured 분석을 작성한다. 분석에 포함할 요소:
  1. **추정 원인 (estimated_cause)**: 실적발표, 뉴스/공시, 섹터 동반 상승, 기술적 돌파, 시간외 재료, M&A/이슈, 알 수 없음 중 선택
  2. **선행 지표 (leading_indicators)**: 급등 전에 감지 가능했을 신호 (예: "전일 시간외 +3%", "3일 연속 거래량 증가")
  3. **정보 갭 (information_gap)**: 현재 autostock 데이터로 설명되지 않는 부분, 수집할 수 있었다면 도움 되었을 데이터 소스
- **FR-3.3**: Agent 분석 결과는 각 급등주 레코드의 `analysis` 필드에 append된다.
- **FR-3.4**: Agent가 분석을 완료하면 원본 jsonl 파일에 `analysis` 필드가 추가된 레코드를 업데이트한다.

### FR-4: 정보 갭 추적 (Information Gap Tracking)
- **FR-4.1**: Agent가 식별한 정보 갭은 `information_gap` 필드에 자유 텍스트로 기록된다.
- **FR-4.2**: 주기적으로(예: 주간 리뷰) 정보 갭을 집계하여, 가장 빈번하게 등장하는 missing data source를 식별할 수 있는 기초 데이터를 제공한다.
- **FR-4.3**: 정보 갭 데이터는 operator가 `steering/` 채널을 통해 조회 가능해야 한다.

### FR-5: Operator 가시성 (Operator Visibility)
- **FR-5.1**: `steering/watch_surge/` 디렉토리는 F4 steering 채널의 read-view 범위 내에 있어 operator가 조회 가능하다.
- **FR-5.2**: Operator는 `/steer_read` 등을 통해 당일 급등주 리스트와 agent 분석 결과를 확인할 수 있다.

---

## 2. Non-Functional Requirements

### NFR-1: 성능 (Performance)
- **NFR-1.1**: 유니버스 전체(약 100개 종목)의 EOD 가격 데이터 조회 및 급등 감지는 30초 이내에 완료되어야 한다.
- **NFR-1.2**: Agent 분석은 기존 EOD 리뷰 turn 내에서 실행되며, 급등주가 없는 경우 LLM 호출 없이 스킵된다.

### NFR-2: 신뢰성 (Reliability)
- **NFR-2.1**: 가격 데이터 조회 실패는 개별 종목 단위로 격리된다 (한 종목 실패가 전체 감지를 중단하지 않음).
- **NFR-2.2**: JSONL 파일 쓰기는 append-only atomic write로 수행된다.

### NFR-3: 확장성 (Extensibility)
- **NFR-3.1**: 급등 감지 로직(임계값, 조건)은 설정 파일에서 조정 가능해야 한다.
- **NFR-3.2**: 데이터 모델은 추후 급등주 예측 모델의 학습 데이터로 사용될 수 있도록 정형 필드를 포함해야 한다.

### NFR-4: 보안 (Security)
- **NFR-4.1**: 별도 보안 규칙 없음 (PoC 성격, Q7-1=B). 단, steering 채널의 기존 보안 경계(Token 기반) 내에서 동작한다.

---

## 3. 아키텍처 결정 (Architectural Decisions)

| 결정 | 내용 | 근거 |
|------|------|------|
| **모듈 위치** | `src/surge/` 독립 모듈 | Q6=B, 일별 데이터만 필요 → intraday 시스템 의존 불필요 |
| **데이터 저장** | `steering/watch_surge/YYYY-MM-DD.jsonl` | Q4=X, C2=A, operator 가시성 확보 |
| **실행 시점** | EOD 단일 실행 | Q5=A, 일별 급등 감지에 충분 |
| **분석 방식** | Agent semi-structured 자연어 분석 | Q2=B, C3=A — 자유 텍스트 + 구조적 가이드 |
| **급등 임계값** | +7% (설정 가능) | C1=B, `surge.threshold_pct` |
| **기존 시스템** | 독립 (intraday 시스템과 분리) | Q6=B, 일봉 데이터만 사용 |

---

## 4. 핵심 요약

> 매일 EOD에 유니버스 전체 종목의 일간 등락률을 스캔하여 +7% 이상 급등한 종목을 감지, `steering/watch_surge/`에 JSONL로 기록한다. EOD agent 리뷰 시 급등주 리스트를 제공하여 semi-structured 원인 분석(추정 원인, 선행 지표, 정보 갭)을 수행하고, 분석 결과를 같은 레코드에 append한다. 독립 모듈(`src/surge/`)로 구현하며, operator는 steering 채널을 통해 조회 가능하다.
