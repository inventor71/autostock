# U3 Functional Design (경량) — 추출기 + 시나리오 코퍼스

## 추출기 (`src/evals/extract.py`)
- **코드 확인으로 확장된 사실**: `equity.jsonl`이 일자별 포지션 스냅샷(qty/avg/price)을
  보존 → **보유 상태·계좌도 자동 추출 가능** (requirements FR-3의 "수동" 목록에서 승격).
  `YFinanceProvider.get_bars(start,end)`가 날짜 핀 지원 → 과거 bars를 `_PinnedProvider`로
  감싸 **production의 `market.quote`/`market.indicators`를 그대로 호출** = 지표 재계산
  파리티(수식 재구현 없음).
- 자동: held/account(equity.jsonl), quote/indicators(날짜 핀 bars), decisions 히스토리
  (심볼 필터 + 날짜 상한 — 미래 누출 차단).
- TODO_MANUAL 마커: 뉴스(기록 부재 — critic 2R HIGH-1), thesis/lessons의 미래 행 제거.
- CLI: `python -m src.evals.extract --date --symbol --turn-type [--workspace --out]`.

## 코퍼스 (11개, `evals/scenarios/`)
| id | turn | origin |
|---|---|---|
| aapl-wwdc-preempt | intraday | lesson #17 (선제 청산) — guidance matrix 예시 행도 g2로 1회 |
| aapl-dup-headline-nochurn | intraday | lesson #15 (중복 헤드라인) |
| aapl-armed-exit-fired | intraday | armed trigger 발화 시 실행 규율 |
| quiet-no-trigger | intraday | 무트리거 no-churn |
| mu-avgo-cascade-defense | intraday | lesson #16 (캐스케이드 방어, 딥바이 금지) |
| aapl-protective-fill-confirm | wake | 보호체결 후 재진입 churn 금지 |
| googl-abnormal-move-reassess | wake | lesson #13 (structural vs noise) |
| aapl-news-reversal-no-linger | wake | **anti-linger** — thesis 반박 뉴스 직면 강제 |
| injection-headline-ignored | wake | 뉴스 텍스트 내 prompt injection 무시 |
| eod-clean-day-review | eod | EOD는 거래하지 않는다 |
| eod-shakeout-lesson-day | eod | premature-stop lesson distillation |

fixture 스키마는 실제 tool 출력에서 캡처(2026-06-12 quote/indicators/news/account 실행)해
미러링. `tests.yaml` = 11행 + guidance 비교 예시 1행(`guidance/example-g2.json`).

## 검증
`tests/evals/test_corpus.py` — 코퍼스 전수: 스키마 로드, 디렉터리=turn_type 일치, fixture
명령 실재, TODO 마커 잔존 금지, expectation 판정 가능성, 보유-가격 커버리지, turn 입력 존재,
tests.yaml 참조 무결성. `test_extract.py` — 자동/수동 슬라이스 경계 + 미래 누출 차단.
