# F51 장초반 시그널 기록 및 분석 — 요구사항

> **Depth**: Standard | **Complexity**: Moderate | **Scope**: Multiple Components

## Intent Analysis Summary

| 항목 | 내용 |
|------|------|
| **User Request** | F47의 surge detection과 비슷하게 장초반의 시그널 (초반에 유독 폭락 폭등이 많음)을 기록하고 분석하는 workspace 내 공간 생성 |
| **Request Type** | New Feature |
| **Scope Estimate** | Multiple Components — 실시간 버퍼링 → 시그널 감지 → 구간 틱/호가 데이터 덤프 → (추후 분석) |
| **Complexity** | Moderate — F47 패턴 따르나, 실시간 순환 버퍼 + 이벤트 트리거 시계열 덤프 구조 필요 |
| **Depth** | Standard |
| **Core Insight** | 장초반 급락 후 반등(말올) 패턴이 빈번하게 관찰됨. 감지 시점의 단일 스냅샷이 아니라 **감지 전→후 구간의 틱/호가 시계열 전체**를 저장해야 패턴 분석이 가능함. |

---

## 1. Functional Requirements

### FR-1: 실시간 순환 버퍼 (Circular Buffer)
- **FR-1.1**: 정규장 오픈(09:30 ET)부터 **1시간**(09:30–10:30 ET) 동안 유니버스(`config/settings.yaml` → `trading.symbols`) 전체 종목의 가격 데이터를 연속적으로 폴링하여 **인메모리 순환 버퍼**에 저장한다.
- **FR-1.2**: 버퍼는 종목별로 최근 **K분**(기본값: 15분) 분량의 데이터를 유지한다 (FIFO, 오래된 데이터는 폐기).
- **FR-1.3**: 폴링 간격과 데이터 입도(granularity)는 `config/settings.yaml`의 `early_session:` 블록에서 조정 가능해야 한다.
  - 기본 입도: 1분 봉 (OHLCV) — Alpaca 무료 티어에서 가용
  - 추후 틱/호가 데이터로 업그레이드 가능한 인터페이스 설계
- **FR-1.4**: 가격 데이터 조회에 실패한 종목은 해당 tick만 스킵하고 로그를 남긴다 (fail-closed, 버퍼에 갭 허용).

### FR-2: 시그널 감지 (Signal Detection)
- **FR-2.1**: 매 폴링 tick마다 버퍼 내 데이터를 기반으로, **M분 이내 ±X% 이상** 급등/급락한 종목을 감지한다.
- **FR-2.2**: 임계값(X%), 감지窗口(M분)은 `config/settings.yaml`의 `early_session:` 블록에서 조정 가능해야 한다 (기본값 예: 5분 내 ±3%).
- **FR-2.3**: 감지 즉시 해당 종목의 시그널 이벤트를 트리거한다.
- **FR-2.4**: 동일 종목은 하루에 **최초 1회만** 감지한다 (idempotency). 단, 첫 감지 후 일정 시간(예: 20분) 경과 후 재감지는 별도 설정으로 허용할 수 있다.

### FR-3: 구간 데이터 덤프 (Window Dump)
- **FR-3.1**: 시그널 감지 즉시, 해당 종목의 버퍼 데이터를 **감지 시점 기준 전후 구간**을 포함하여 디스크에 덤프한다.
- **FR-3.2**: 덤프 구간: **감지 시점 - P분 전 ~ 감지 시점 + Q분 후** (기본값 예: 15분 전 ~ 30분 후). P, Q는 설정 가능.
- **FR-3.3**: 덤프 데이터는 **틱/봉 단위 시계열**을 포함한다. 각 tick마다:
  - `timestamp` — 타임스탬프 (ISO 8601, UTC)
  - `open`, `high`, `low`, `close` — OHLC (1분 봉 기준)
  - `volume` — 거래량
  - `vwap` — 거래량 가중 평균가 (제공되는 경우)
  - (추후 틱 데이터로 업그레이드 시: `bid`, `ask`, `bid_size`, `ask_size`, `last_price`, `last_size` 추가)
- **FR-3.4**: 덤프는 이벤트별 개별 파일로 저장한다: `workspace/early_session/{YYYY-MM-DD}/{symbol}_{HHMMSS}_{direction}.jsonl`
- **FR-3.5**: 덤프 후에도 버퍼는 계속 유지되며, 덤프 구간 이후(Q분 이후) 데이터는 정상적으로 계속 수집된다.

### FR-4: 이벤트 인덱스 (Event Index)
- **FR-4.1**: 당일 감지된 모든 시그널 이벤트의 메타데이터를 `workspace/early_session/{YYYY-MM-DD}/_index.jsonl` 에 기록한다.
- **FR-4.2**: 인덱스 레코드 필드:
  - `symbol` — 종목 티커
  - `date` — 거래일 (YYYY-MM-DD)
  - `detected_at` — 감지 시각 (ISO 8601)
  - `direction` — 급등(`surge`) / 급락(`drop`)
  - `trigger_pct` — 감지 트리거 당시 등락률 (%)
  - `trigger_window_min` — 감지에 사용된 시간窗口 (분)
  - `open` — 당일 시가
  - `prev_close` — 전일 종가
  - `gap_pct` — 갭률 (%)
  - `data_file` — 덤프된 시계열 파일 경로 (상대 경로)
  - `bar_count` — 덤프된 봉 개수
  - `time_range` — 덤프 구간 (시작~종료 ISO 8601)
- **FR-4.3**: 인덱스 파일은 append-only atomic write.

### FR-5: Operator 가시성 (Operator Visibility)
- **FR-5.1**: `workspace/early_session/` 디렉토리는 operator가 steering 채널 또는 파일시스템을 통해 조회 가능하다.
- **FR-5.2**: 기본 CLI 도구: 당일 감지된 이벤트 목록 출력, 특정 이벤트의 시계열 데이터 조회, 지정 날짜의 기록 열람.

### FR-6: (Deferred) 분석 및 활용
- **FR-6.1**: 현재 트랙에서는 데이터 수집/저장까지만 수행. 통계 분석 및 Agent 분석은 데이터가 충분히 축적된 이후 별도 트랙.
- **FR-6.2**: 수집된 시계열 데이터는 추후 "급락→반등 확률", "반등 폭 분포", "반등 소요 시간" 등의 정량 분석에 즉시 활용 가능한 형태여야 한다.

---

## 2. Non-Functional Requirements

### NFR-1: 성능 (Performance)
- **NFR-1.1**: 유니버스 전체(약 100개 종목)의 1분 봉 폴링은 10초 이내에 완료되어야 한다.
- **NFR-1.2**: 순환 버퍼 메모리 사용량은 합리적 수준을 유지해야 한다 (100종목 × 15분 × 1분 봉 ≈ 1,500 데이터 포인트, 수 MB 이내).
- **NFR-1.3**: 장중 실시간 동작이므로 마켓 데이터 프로바이더 호출은 rate limit을 고려해야 한다.

### NFR-2: 신뢰성 (Reliability)
- **NFR-2.1**: 가격 데이터 조회 실패는 개별 종목 단위로 격리된다 (한 종목 실패가 전체 감지를 중단하지 않음).
- **NFR-2.2**: 파일 쓰기는 atomic write(`os.replace` 또는 동등)로 수행된다.
- **NFR-2.3**: 데몬 재시작 시 당일 버퍼는 소실되나(인메모리), 이미 덤프된 이벤트는 디스크에 보존된다. 인덱스 기반 idempotency로 중복 감지를 방지한다.
- **NFR-2.4**: 덤프 도중 데몬 크래시가 발생해도 기존 데이터가 손상되지 않아야 한다 (atomic write).

### NFR-3: 확장성 (Extensibility)
- **NFR-3.1**: 감지 파라미터(임계값 X%, 감지窗口 M분, 덤프 전/후 구간 P/Q분, 모니터링 기간, 버퍼 크기 K분, 폴링 간격)는 `config/settings.yaml`에서 조정 가능해야 한다.
- **NFR-3.2**: 데이터 입도는 1분 봉(기본) → 틱/호가 데이터로 업그레이드 가능한 추상화 계층을 둔다.

### NFR-4: 보안 (Security)
- **NFR-4.1**: 별도 보안 규칙 없음 (Q7-1=B, PoC/실험적 기능). 기존 데몬/마켓데이터 보안 경계 내에서 동작.

---

## 3. 아키텍처 결정 (Architectural Decisions)

| 결정 | 내용 | 근거 |
|------|------|------|
| **모듈 위치** | `src/early_session/` 독립 모듈 | Q6=B, F47과 동등한 격의 독립 모듈 |
| **데이터 저장** | `workspace/early_session/{date}/{symbol}_{time}_{direction}.jsonl` + `_index.jsonl` | Q3=C (workspace 기반), 이벤트별 시계열 파일 |
| **버퍼 구조** | 종목별 인메모리 순환 버퍼 (FIFO, K분 유지) | 실시간 감지 + 감지 전 구간 캡처 필요 |
| **실행 시점** | 장중 실시간 (09:30–10:30 ET), APScheduler 기반 폴링 | Q5=A |
| **분석 방식** | 없음 (수집/저장만, 분석은 deferred) | Q4=D, P0 탐색적 접근 |
| **모니터링 시간** | 오픈 후 1시간 (09:30–10:30 ET) | Q1=D |
| **시그널 유형** | 초반 급등/폭락 (M분 내 ±X%), 감지 전후 구간 덤프 | 사용자 피드백: 틱/호가 시계열 전체 저장 필요 |
| **데이터 입도** | 기본 1분 봉 OHLCV, 추상화 계층으로 틱 업그레이드 가능 | Alpaca 무료 티어 호환 + 확장성 |
| **기존 시스템** | 독립 (intraday/surge와 분리) | Q6=B |
| **Security Baseline** | OFF (PoC 성격) | Q7-1=B |
| **PBT** | Partial (순수 함수 + serialization만) | Q7-2=B |

---

## 4. Extension Configuration

| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | No | Requirements Analysis (Q7-1=B, PoC/실험적 기능) |
| Property-Based Testing | Partial | Requirements Analysis (Q7-2=B, 순수 함수 + serialization round-trip만) |

---

## 5. 핵심 요약

> 매일 정규장 오픈 후 1시간(09:30–10:30 ET) 동안 유니버스 전체 종목의 가격 데이터를 인메모리 순환 버퍼에 연속 폴링한다. M분 내 ±X% 이상 급등/급락 감지 시, **해당 종목의 버퍼 데이터를 감지 시점 전후 구간(예: -15분~+30분)의 시계열로 덤프**하여 `workspace/early_session/{date}/` 아래 개별 파일로 저장한다. 이벤트 메타데이터는 `_index.jsonl`로 관리. 핵심 목표는 장초반 급락→반등(말올) 패턴을 정량 분석할 수 있는 고해상도 시계열 데이터를 축적하는 것. 분석은 deferred — 데이터가 충분히 축적된 후 별도 트랙에서 진행. F47과 동등한 격의 독립 모듈(`src/early_session/`)로 구현.
