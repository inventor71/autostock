# Unit 1: signal-tools — Code Generation Plan

## 개요
시그널 도구 확장 + retrospect 구조화 + config 모델. 기존 아키텍처 변경 없음.

## 선행 조건
- [x] Requirements Analysis 승인
- [x] Workflow Planning 승인
- [x] Worktree 생성 (Part 2 첫 단계)

## Step 0: Worktree 생성
- [x] `git worktree add .claude/worktrees/F23 -b feat/F23` (base: 620eeac)
- [x] worktree에서 작업 시작

## Step 1: Config 모델 확장 (`config/config.py`) — DONE
- [x] `AgentConfig`에 필드 추가:
  - `research_start_before_open: int = 60`
  - `research_end_before_open: int = 5`
- [x] `MultiAgentConfig(BaseModel)` 추가:
  - `enabled: bool = False`
  - `mode: str = "sequential"` (sequential | parallel)
  - `n_agents: int = 3` (범위 [1,5])
- [x] `ResearchSignalsConfig(BaseModel)` 추가:
  - `signals: list[str]` (기본값: 현재 전체 목록)
- [x] `ReflectionConfig(BaseModel)` 추가:
  - `enabled: bool = True`
  - `max_lessons_injected: int = 10`
- [x] `Settings`에 필드 등록:
  - `multi_agent: MultiAgentConfig = MultiAgentConfig()`
  - `research: dict = {}` (F3 `intraday` 패턴과 동일 — 유연한 dict, 소비자가 파싱)
- [x] validation: `multi_agent.enabled=True`이면 `n_agents >= 2` 강제
- [x] 테스트: config round-trip (yaml → Settings → 필드 접근)

## Step 2: `_FUNDAMENTAL_KEYS` Short Interest 확장 (`market.py`)
- [x] `_FUNDAMENTAL_KEYS` 튜플에 추가:
  - `"shortRatio"`, `"shortPercentOfFloat"`, `"heldPercentInsiders"`, `"heldPercentInstitutions"`
- [x] 테스트: 기존 `fundamentals()` 테스트에 새 키 확인 추가

## Step 3: 새 독립 도구 — `earnings()` (`market.py`)
- [x] 함수 시그니처: `earnings(symbol: str, ticker_factory=None) -> dict`
- [x] `ticker.calendar` → 다음 earnings date, EPS/Revenue estimate
- [x] `ticker.earnings_dates` → 최근 4분기 실적 surprise history (try/except — lxml 없으면 `calendar`만)
- [x] 출력: `{symbol, next_earnings_date, days_until_earnings, consensus_eps, consensus_revenue, surprise_history: [{date, reported_eps, estimated_eps, surprise_pct}]}`
- [x] 빈 DataFrame / None 처리
- [x] 테스트: mock ticker_factory, lxml 있는/없는 경우

## Step 4: 새 독립 도구 — `insider()` (`market.py`)
- [x] 함수 시그니처: `insider(symbol: str, ticker_factory=None) -> dict`
- [x] `ticker.insider_transactions` → DataFrame (Insider, Start Date, Transaction, Shares, Value 등)
- [x] 출력: `{symbol, recent_transactions: [{insider, date, type, shares, value}], summary: {total_buys, total_sells, net_shares, largest_buy}}`
- [x] 최근 6개월 필터, 최대 20건
- [x] 빈 DataFrame 처리
- [x] 테스트: mock ticker_factory

## Step 5: 새 독립 도구 — `analyst_upgrades()` (`market.py`)
- [x] 함수 시그니처: `analyst_upgrades(symbol: str, ticker_factory=None) -> dict`
- [x] `ticker.upgrades_downgrades` → DataFrame (GradeDate, Firm, ToGrade, FromGrade, Action)
- [x] 출력: `{symbol, recent: [{date, firm, action, from_grade, to_grade}], count_upgrade, count_downgrade}`
- [x] 최근 5건
- [x] 빈 DataFrame 처리
- [x] 테스트: mock ticker_factory

## Step 6: 새 독립 도구 — `institutional()` (`market.py`)
- [x] 함수 시그니처: `institutional(symbol: str, ticker_factory=None) -> dict`
- [x] `ticker.institutional_holders` → DataFrame (Holder, Shares, Date Reported, % Out, Value)
- [x] 출력: `{symbol, institutional_pct, top_holders: [{name, pct, shares, date}]}`
- [x] top 5, total % 합산
- [x] 빈 DataFrame 처리
- [x] 테스트: mock ticker_factory

## Step 7: 새 독립 도구 — `macro()` (`market.py`)
- [x] 함수 시그니처: `macro(provider=None) -> dict`
- [x] yfinance로 quote 조회: `^TNX` (10Y yield), `^FVX` (5Y yield), `DX-Y.NYB` (Dollar Index), `GC=F` (Gold), `CL=F` (Oil), `^VIX` (VIX)
- [x] 각 시리즈: latest price + 1d change
- [x] 출력: `{as_of, treasury_10y, treasury_5y, dollar_index, gold, oil, vix}` 각각 `{price, change_1d_pct}`
- [x] 개별 실패 허용 (하나가 실패해도 나머지 반환)
- [x] 테스트: mock provider

## Step 8: Retrospect — `LessonRecord` + `lesson add` CLI (`journal.py` + `market.py` + `__main__.py`)
- [x] `journal.py`에 `LessonRecord(BaseModel)` 추가:
  ```python
  class LessonRecord(BaseModel):
      lesson_id: str  # "L001", auto-increment
      date: str       # ISO date
      category: str   # entry_timing | exit_timing | risk_mgmt | regime | thesis | sizing | other
      signal_used: str
      outcome: str
      takeaway: str
      times_applied: int = 0
  ```
- [x] `Journal`에 메서드 추가:
  - `lessons_jsonl` property → `self.root / "lessons.jsonl"`
  - `read_lessons_jsonl() -> list[LessonRecord]` (torn-safe 읽기)
  - `append_lesson_record(record: LessonRecord)` (atomic append + lessons.md 동시 갱신)
  - `next_lesson_id() -> str` (max id + 1)
- [x] `market.py`에 `lesson_add()` 함수는 불필요 — CLI 레벨에서 직접 Journal 호출
- [x] `__main__.py`에 `lesson add` 서브커맨드:
  ```
  python -m src.agent.tools lesson add --category <cat> --signal "<sig>" --outcome "<out>" --takeaway "<take>"
  ```
  → Journal().append_lesson_record(record) 호출 → JSON 출력
- [x] 테스트: LessonRecord round-trip (PBT: Hypothesis), append/read, lesson_id auto-increment

## Step 9: `__main__.py` — 새 서브커맨드 등록
- [x] `earnings`, `insider`, `analyst_upgrades`, `institutional` → 각각 symbol 인자
- [x] `macro` → 인자 없음
- [x] `lesson` → add 서브커맨드 (Step 8)
- [x] 기존 dispatch 패턴 (`if args.cmd == ...`) 따름

## Step 10: `settings.yaml` 업데이트
- [x] `multi_agent:` 블록 추가 (기본값으로, enabled: false)
- [x] `agent:` 블록에 `research_start_before_open: 60`, `research_end_before_open: 5` 추가
- [x] (research.signals는 dict 패턴이므로 yaml에 기본 목록 추가)

## Step 11: 테스트 통합 + 회귀
- [x] 새 도구 단위 테스트 전부 통과 확인
- [x] PBT: LessonRecord round-trip (Hypothesis)
- [x] PBT: config validation (n_agents 범위, enabled+n_agents 제약)
- [x] 기존 전체 테스트 회귀 없음 확인
- [x] DESIGN.md / README에 새 도구 언급 (최소한의 문서 갱신)

## 변경 파일 요약
| 파일 | 변경 |
|------|------|
| `config/config.py` | AgentConfig 확장 + MultiAgentConfig + Settings 필드 |
| `config/settings.yaml` | multi_agent + agent timing + research 블록 |
| `src/agent/tools/market.py` | `_FUNDAMENTAL_KEYS` 확장 + earnings/insider/analyst_upgrades/institutional/macro 함수 |
| `src/agent/tools/__main__.py` | 6개 새 서브커맨드 등록 |
| `src/agent/journal.py` | LessonRecord + lessons.jsonl 메서드 |
| `tests/` | 새 도구 테스트 + PBT |

## yfinance API 리스크 (실 호출로 확인됨)

| 리스크 | 대응 |
|--------|------|
| **ETF(SPY 등)는 fundamentals/insider/calendar 404** → 빈 DataFrame/dict 반환 | 모든 새 도구에서 빈 결과 graceful 처리. `{"symbol": "SPY", "error": "no data"}` 패턴 |
| **`earnings_dates` lxml 필수** → `ImportError` | try/except, `calendar`만으로 폴백 (surprise history 없이 다음 earnings date + estimate만) |
| **`calendar` 키 불일치** (배당 없는 종목은 Dividend Date 없음) | 모든 키 `.get()` 접근 |
| **`insider_transactions` 실 컬럼**: `['Shares', 'Value', 'URL', 'Text', 'Insider', 'Position', ...]` (계획의 `Transaction` ≠ 실제 `Text`) | 실제 컬럼명 기준 구현 |
| **`upgrades_downgrades` 실 컬럼**: `['Firm', 'ToGrade', 'FromGrade', 'Action', 'priceTargetAction', 'currentPriceTarget']`, 날짜는 인덱스 | `.index` 접근 + 실 컬럼명 |
| **yfinance 스크래핑 불안정** (Yahoo 변경 시 경고 없이 깨짐) | per-property try/except, 개별 실패가 전체를 sink하지 않도록 |
| **매크로 심볼 전부 정상 확인** (`^TNX`, `DX-Y.NYB`, `GC=F`, `CL=F`, `^VIX`) | 개별 실패 허용 설계 유지 |

Alpaca API: Unit 1에 변경 없음.

## 예상 범위
- 새 코드: ~300-400 라인 (market.py ~200, journal.py ~60, config.py ~40, __main__.py ~60)
- 새 테스트: ~200-300 라인
- 0 new runtime dependencies (yfinance 기존 사용, lxml은 optional)
