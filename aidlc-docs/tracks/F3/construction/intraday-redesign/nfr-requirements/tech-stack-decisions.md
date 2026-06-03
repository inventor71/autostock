# Tech-Stack Decisions — Intraday 루프 재설계 (F3)

> Unit `intraday-redesign`. **신규 런타임 의존성 0** — 본 문서는 그 판정 근거와 재사용 매핑.

## 결정 요약
| 영역 | 선택 | 신규 dep |
|---|---|---|
| 동시성 | stdlib `threading`(Lock/Timer/Thread) — main TurnCoordinator/ReconcileWorker 재사용·수정 | 없음 |
| 트리거 버퍼 | stdlib `queue.Queue` 또는 list+Lock(WakeDetector 소유 typed-event 버퍼) | 없음 |
| 직렬화/모델 | `pydantic`(기존) — WatchTrigger/WakeEvent/FillDelta 등 레코드 | 없음 |
| 영속(JSONL/커서/fired-set) | stdlib `json` + main `jsonl.py`(read_complete_lines/ByteCursor/atomic_write_text) | 없음 |
| 스케줄 | `APScheduler`(기존) — wake detector job + 15분 스케줄 turn | 없음 |
| broker 체결 | `alpaca-py`(기존) raw `TradingClient.get("/account/activities")` + `TradeActivity` 파싱 | 없음 |
| 시장데이터/지표 | 데몬 `data_provider`(기존, alpaca/yfinance) `get_bars`/`get_latest_price` | 없음 |
| 뉴스 | `news_provider`(기존 yfinance) 별도 스레드 폴링 | 없음 |
| 로깅 | `loguru`(기존) — heartbeat/보류/예외 best-effort | 없음 |
| 테스트 | `pytest` + `Hypothesis`(기존 dev) — 예제 + PBT 불변식 | 없음 |

## 핵심 근거 — 왜 신규 dep가 필요 없나
1. **동시성 엔진은 main에 이미 존재**(F4): turn_lock·skip-if-busy·per-kind reconcile·bus single-worker. F3는 *수정·확장*만(레인 분리, 페이로드 확장) — 새 라이브러리 불요.
2. **체결 진실(activities)**: alpaca-py가 Trading 클라이언트에 typed 래퍼를 안 줘도, **베이스 `RESTClient.get`** 로 `/account/activities` 엔드포인트 직접 호출 가능(경로에 `/v2` 붙이지 않음 — `get`이 버전 prepend, 2차 critic#9). `TradeActivity`/`ActivityType.FILL`이 SDK에 있어 파싱도 기존 모델로. → **dep 추가 없이** Q3=A(활동내역) 실현.
3. **brief/감지/뉴스/watch**는 전부 파일·stdlib·기존 provider 조합.

## 리스크/검증 항목 (NFR Design·Code Gen으로)
- **R1 (raw activities GET)**: `TradingClient.get` 경로/파라미터(`activity_types=FILL`, `after`/`page_token` 페이지네이션, ET 타임존) — **paper 계정 라이브 검증 필수**(타입 래퍼 없음). 실패 시 fallback = 주문상태 전이(부분체결 맹목, BR-7 열등 경로)로 degrade, fail-closed.
- **R2 (뉴스 블로킹)**: `yf.Ticker().news`는 블로킹·레이트리밋 → 반드시 별도 스레드 + best-effort(설계상 OK, 트리거 아님).
- **R3 (바 fetch 비용)**: `get_bars` 무캐시 → 캐시 계층 신규(stdlib dict+ts), dep 아님.

## SECURITY (Baseline, 해당분만)
- **SECURITY-03**: brief/로그/watch에 비밀 미포함. activities 응답에 계정 식별자 있으면 로그에서 스크럽.
- **SECURITY-10**(dep 핀): 신규 dep 0 → 신규 핀 항목 없음.
- **SECURITY-15**(fail-closed): activities/바/watch 파싱 실패는 보수적 처리(억제 쪽). 그 외 N/A(웹앱/DB/IaC/인증 없음).
