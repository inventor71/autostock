# F70 / benchmark — Build & Test Summary

## 빌드
- Python only. 신규 의존성 없음(표준 lib + 기존 pydantic/loguru/pandas/jsonl 헬퍼 재사용).
- 빌드 단계 없음(인터프리티드). import 정합성은 스모크로 검증.

## 단위 테스트 (tests/benchmark/) — `pytest tests/benchmark -q`
**결과: 30 passed.**
- `test_buy_and_hold.py` — 미보유→BUY, 보유→HOLD, 타 종목 보유 시 BUY, 빈 bars→InsufficientDataError, 레지스트리 등록
- `test_config.py` — 기본 OFF, EOD/분 인터벌, 잘못된 인터벌 폴백, 계정 누락 경고, benchmark 속성 부재
- `test_store.py` — append↔load 라운드트립, **시크릿 미포함(account_masked만)**, 비유한 equity 스킵, retention 컴팩션
- `test_metrics.py` — 누적수익/alpha 정의, MDD 음수, llm 없을 때 alpha 없음, **공통 window 절단**, 단일점 0, **PBT 순수성(동일입력=동일출력, MDD≤0)**
- `test_runner.py` — 계정누락 스킵, **라이브 계정 충돌 스킵(NFR-1)**, 브로커 빌드실패 격리, **data_provider 공유**, baseline+LLM 기록, **tick 예외 격리**, toggle off no-op, 생존 baseline 0이면 미기동

## 통합 / 스모크
- settings.yaml 로드 → BenchmarkConfig 파싱: **enabled=false 기본 확인**(agent 경로 무영향).
- buy_and_hold 레지스트리 등록 확인.
- metrics CLI: 빈 디렉토리 → exit 1(graceful); 해피패스 E2E(llm +25%/rsi +5% → **alpha +20%**, metrics 파일 생성) 확인.
- `main.py` 파싱 OK(헬퍼 문법).

## 인접 회귀
- `tests/test_strategies.py + test_jsonl.py + test_core.py` — **35 passed** (전략 레지스트리·jsonl·core 모델 무회귀).

## NFR 검증 매핑
| NFR | 상태 |
|-----|------|
| 1 프로덕션 무영향 | ✅ toggle off no-op + 라이브 계정 충돌 스킵 + tick 예외 격리 테스트 |
| 2 운영 부담 | ✅ data_provider 공유 테스트 + EOD 기본 cadence |
| 3 저장 비용 | ✅ retention 컴팩션 테스트 |
| 4 재현성 | ✅ compute 순수성 PBT + CLI 재산출 E2E |
| 5 보안 | ✅ 스냅샷 시크릿 미포함 테스트 + account_masked |

## 알려진 한계 / 실사용 전제 (Post-Merge Guide 참조)
- baseline이 **실제로 거래하려면** sandbox 계정을 만들어 `benchmark.accounts`에 매핑하고
  `enabled: true`로 켜야 함(기본 OFF). 계정 미구성 시 fail-closed로 조용히 스킵.
- EOD cadence는 "하루 1회"(정확한 장마감 시각 동기화 아님) — 비교 목적엔 충분.
