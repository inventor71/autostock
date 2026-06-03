# surge-detection — NFR Requirements

> Minimal Depth | 2026-06-03

## Assessment Summary

EOD 배치 작업 + agent tool. 단순 데이터 파이프라인으로 NFR 요구사항이 제한적임.

---

## NFR-1: Performance

| ID | Requirement | Target | Rationale |
|----|-------------|--------|-----------|
| NFR-1.1 | 유니버스 전체 scan 소요 시간 | ≤ 30초 (100종목 기준) | EOD flow blocking 없이 충분, yfinance API rate limit 고려 |
| NFR-1.2 | 개별 종목 데이터 조회 | ≤ 2초/종목 | yfinance 단일 종목 history 호출 기준 |
| NFR-1.3 | Agent tool 응답 시간 | ≤ 1초 | 로컬 JSONL 파일 읽기, 네트워크 I/O 없음 |

---

## NFR-2: Reliability

| ID | Requirement | Implementation |
|----|-------------|----------------|
| NFR-2.1 | Per-symbol fail isolation | 개별 종목 예외 → skip + log, 전체 scan 중단 없음 |
| NFR-2.2 | Atomic file write | temp file + `os.replace()`, 부분 파일 노출 방지 |
| NFR-2.3 | Market holiday detection | `MarketClock.is_market_open()` 체크, 휴장일 scan skip |
| NFR-2.4 | Data provider timeout | API 호출 10초 timeout, 초과 시 None 반환 |

---

## NFR-3: Extensibility

| ID | Requirement |
|----|-------------|
| NFR-3.1 | `threshold_pct` 설정 파일에서 조정 가능 |
| NFR-3.2 | `SurgeCause` enum 확장 가능 (신규 원인 추가 용이) |
| NFR-3.3 | DataProvider interface 기반으로 provider 교체 가능 (yfinance ↔ Alpaca) |

---

## NFR-4: Security

| ID | Requirement | Note |
|----|-------------|------|
| NFR-4.1 | Security Baseline extension 비활성화 (Q7-1=B) | PoC 성격 |
| NFR-4.2 | Agent tools는 daemon context에서 실행 → steering/ 접근 가능 | 기존 agent tool 아키텍처 재사용 |
| NFR-4.3 | 민감 정보 없음 — market data + agent 분석 텍스트만 저장 | API key, 계좌 정보 등 미포함 |

---

## NFR-5: Maintainability

| ID | Requirement |
|----|-------------|
| NFR-5.1 | `src/surge/` 단일 패키지, 4개 모듈 (records, detector, store, settings) |
| NFR-5.2 | 기존 `src/agent/steering/jsonl.py`의 `read_complete_lines` + `atomic_write_text` 재사용 |
| NFR-5.3 | Agent tool은 기존 `src/agent/tools/__main__.py` CLI 패턴 따름 |
