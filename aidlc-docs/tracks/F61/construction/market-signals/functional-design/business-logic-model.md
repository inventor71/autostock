# F61 Functional Design — Business Logic & Architecture (unit: market-signals)

## 레이어 분리 (테스트성 핵심 — NFR-4)
- **순수 코어** (`src/signals/movers.py`, `peer_map.py`, `readthrough.py`, `earnings_cal.py`, `brief.py`): 입력→출력 결정적, 네트워크·LLM·시계 의존 없음. Tier 1 유닛+PBT 대상.
- **비순수 경계** (`src/signals/collector.py`, `sources/*.py`): HTTP·캐시·시계·키. 타임아웃 바운드 + fail-honest. 얇게 유지하고 순수 코어를 호출.

## 흐름 (SignalCollector.collect())
1. **가격 행 수집**: 기존 provider로 universe ∪ bellwether의 일간 변화율·거래량비 행 확보(기존 `tools.market.scoreboard` 로직 재사용/공유). 타임아웃 바운드, 동시성.
2. **무버 추출**: `detect_movers(rows, thresholds)` (순수).
3. **뉴스 보강(선택)**: 무버 트리거 후보에 한해 NewsSource로 신규 헤드라인 조회 → `cause_hint` 추출(간단 키워드/요약 앞부분). 실패 시 cause_hint=None로 진행(fail-honest).
4. **전파**: `build_readthrough(movers, peer_map, universe)` (순수) — readthrough 임계 이상 무버에 대해 유니버스 피어 도출.
5. **실적 캘린더**: EarningsCalendarSource로 horizon(today..+N)·universe∪held 필터 → `select_imminent_earnings(...)` (순수, 피어맵 교차).
6. **조립**: `assemble_brief(movers, alerts, earnings, degraded_sources)` → MarketSignalBrief (순수).
7. 반환. 호출자: orchestrator(push) / tools(pull). 동일 결과 재사용(중복 산출 금지) — collect()는 짧은 TTL 캐시.

## 순수 함수 시그니처(안)
```python
def detect_movers(rows: list[Row], *, price_pct: float, vol_ratio: float,
                  universe: set[str]) -> list[Mover]
def peers_of(symbol: str, peer_map: PeerMap) -> list[str]
def build_readthrough(movers: list[Mover], peer_map: PeerMap, universe: set[str],
                      *, min_trigger_pct: float, max_peers: int) -> list[ReadThroughAlert]
def select_imminent_earnings(cal: list[EarningsRow], universe: set[str], held: set[str],
                             peer_map: PeerMap, *, horizon_days: int, today: date) -> list[ImminentEarnings]
def assemble_brief(...) -> MarketSignalBrief
```

## 에이전트 노출 (FR-5)
### Push (orchestrator → prompts)
- **모든 research 경로**에 브리프 prepend(critic 반영 — multi-agent 누락 수정): 단일세션 `morning_research_prompt`, sequential `multi_research_initial_prompt`(동일 세션이라 debate/synthesis로 컨텍스트 전파), **parallel `sub_agent_prompt`(특히 discovery 서브에이전트) + `parallel_synthesis_prompt`**. 전부 optional `signal_brief=None`(하위호환).
- parallel은 `_signal_brief()`를 **1회 계산**(collect TTL 캐시)해 모든 서브에이전트에 전달.
- orchestrator는 turn 시작 시 `SignalCollector.collect()` → `to_prompt_text()`를 넘김. collect 실패해도 turn은 진행(brief 생략, NFR-1).

### Pull (신규 툴 — `python -m src.agent.tools <name>`)
| 툴 | 인자 | 출력 |
|---|---|---|
| `movers` | (없음) | 무버 리스트 JSON |
| `readthrough` | `<SYM>` | 해당 종목 트리거 시 유니버스 피어 + groups |
| `earnings_calendar` | `[days]` | 임박 실적 리스트 |
- `tools/__main__.py`에 서브커맨드 등록, 기존 provider/소스 주입. 단위 테스트는 합성 주입.

## 검증 설계 (Q6 2-tier)
### Tier 1 — 자동·토큰 0
- 유닛: 각 순수 함수 example 기반(경계·정렬·상한·degrade).
- **PBT (Partial, Hypothesis — PBT-09 기존 dep)**:
  - PBT-03 invariant: detect_movers 결과 모든 원소가 임계 충족; output symbols ⊆ input; build_readthrough의 affected_peers ⊆ universe ∧ trigger ∉ affected; peers_of(sym) ∌ sym.
  - PBT-02 round-trip: 모든 레코드 `model_validate(x.model_dump()) == x`.
  - PBT-07 도메인 생성기: 심볼/Row/무버 생성기(현실적 범위 — chg_pct∈[-30,30], vol_ratio≥0).
  - PBT-08 시드 재현성: Hypothesis 기본(shrinking on, 실패 시드 로깅).
- **다유형 시나리오 코퍼스**(`tests/signals/scenarios/`): 고정 픽스처(JSON: 입력 rows/news/calendar + expected brief 요지). 시나리오 유형은 business-rules.md S1~S5.
### Tier 2 — 온디맨드·토큰 (자동/CI 미포함 — NFR-7)
- `src/signals/eval_harness.py` + 엔트리포인트 `python -m src.signals.eval_readthrough <scenario_id>`: 시나리오 브리프를 실제 에이전트 세션에 주고 판단 출력. 파일명/위치에 `test_` 미사용 + pytest 수집 경로 밖(또는 `@pytest.mark.manual` + 기본 deselect). CI/기본 pytest에서 LLM 절대 미호출.

## PBT-01 속성 식별 요약
| 컴포넌트 | 카테고리 | 속성 |
|---|---|---|
| detect_movers | Invariant | 임계 충족·부분집합·정렬 |
| peers_of | Invariant/Idempotence | 대칭·self 제외 |
| build_readthrough | Invariant | affected ⊆ universe, trigger∉affected |
| records (de)serialize | Round-trip | dump→validate=identity |
| assemble_brief | (결정성) | 동일 입력 동일 출력 |

## 재사용 (NFR-2/3, NFR-5 — 기존 동작 보존)
- 타임아웃: F14 `install_session_timeout` 패턴.
- 캐시: news 15분 TTL류, collect() 단위 짧은 TTL.
- best-effort/degrade: `NewsPoller` 패턴.
- scoreboard 가격 스캔 로직 공유(중복 금지).
- prompts/tools/orchestrator 변경은 모두 additive·하위호환.
