# F61 Functional Design — Domain Entities (unit: market-signals)

> 기술 비종속 도메인 모델. 구현은 pydantic 모델(`src/signals/records.py`)로 예상.
> 모든 레코드는 직렬화 round-trip 대상(PBT-02).

## 새 패키지 위치
`src/signals/` — 기존 `src/surge/`, `src/early_session/` 와 동급의 독립 서브시스템.
(레코드/순수로직/소스어댑터/수집기/브리프). 에이전트 배선은 `src/agent/tools/` + `src/agent/prompts.py` + `src/agent/orchestrator.py`.

---

## E1. Mover — 무버 (FR-1)
임계를 넘은 가격/거래량 변동 1건.
| 필드 | 타입 | 설명 |
|---|---|---|
| symbol | str | 종목 |
| change_pct | float | 기준 종가 대비 % (음수=하락) |
| volume_ratio | float \| None | 20일 평균 대비 거래량 배수 |
| close | float | 현재가 |
| direction | "up" \| "down" | 부호 |
| in_universe | bool | 거래 유니버스 종목 여부(아니면 bellwether-only) |
| qualified_by | list["price","volume"] | 임계 충족 사유 |

## E2. PeerGroup / PeerMap — 정적 피어 맵 (FR-3)
| 개념 | 표현 | 설명 |
|---|---|---|
| PeerGroup | name + members:list[str] | 예: `semiconductors: [NVDA, AMD, AVGO, QCOM, TXN, INTC, MU, SMH]` |
| PeerMap | groups:list[PeerGroup] + 파생 symbol→groups 역인덱스 | config(`signals.peer_groups`)에서 로드 |
- `peers_of(sym)` = sym이 속한 모든 group의 멤버 합집합 − {sym}. 순수 함수.
- 한 종목이 여러 group에 속할 수 있음(예: AVGO ∈ semiconductors ∧ ai_infra).

## E3. ReadThroughAlert — 전파 경고 (FR-3, 핵심)
한 트리거 무버가 피어들에 주는 read-through 경고 1건.
| 필드 | 타입 | 설명 |
|---|---|---|
| trigger_symbol | str | 큰 변동 종목(유니버스 안/밖 무관) |
| trigger_change_pct | float | 트리거 변동% |
| cause_hint | str \| None | 뉴스에서 추출한 간단 힌트(예: "earnings miss") — 없으면 None |
| affected_peers | list[str] | **유니버스 내** 피어(행동 가능한 것만), abs 영향 추정 정렬 |
| groups | list[str] | 어떤 피어 그룹을 통해 전파되는지 |
- 최종 "정말 영향 있나"는 에이전트 판단(LLM 하이브리드). Python은 후보만 제시.

## E4. ImminentEarnings — 임박 실적 (FR-4)
| 필드 | 타입 | 설명 |
|---|---|---|
| symbol | str | 종목 |
| earnings_date | date | 발표일 |
| when | "bmo"\|"amc"\|"unknown" | 장전/장후(있으면) |
| eps_estimate | float \| None | 컨센서스 EPS |
| is_held | bool | 보유 종목 여부 |
| peer_readthrough | list[str] | 이 실적이 영향 줄 보유/유니버스 피어(피어맵 교차) |

## E5. MarketSignalBrief — 통합 브리프 (FR-5)
push/툴이 공유하는 최종 산출물.
| 필드 | 타입 | 설명 |
|---|---|---|
| as_of | datetime | 생성 시각 |
| movers | list[Mover] | 무버(정렬·상한 N) |
| readthrough_alerts | list[ReadThroughAlert] | 전파 경고 |
| imminent_earnings | list[ImminentEarnings] | 임박 실적 |
| degraded_sources | list[str] | 실패/키부재로 누락된 소스(fail-honest 표식, NFR-1) |
- `to_prompt_text()` → 프롬프트 prepend용 간결 텍스트(순수).
- `to_dict()` → 툴 JSON 출력.

---

## 소스 어댑터(외부 경계 — 비순수, E1~E5와 분리)
| 어댑터 | 1차 | 폴백 | 산출 |
|---|---|---|---|
| NewsSource | **AlpacaNewsProvider**(Benzinga, alpaca-py NewsClient) | 기존 YFinanceNewsProvider | NewsItem(기존 모델 재사용/확장) |
| EarningsCalendarSource | **FinnhubEarningsCalendar**(`/calendar/earnings`) | yfinance per-symbol(약함) | ImminentEarnings 원천 |
| PriceSource | 기존 BaseDataProvider(yfinance/alpaca) | — | Mover 입력(scoreboard류 행) |

## 관계도(텍스트)
```
PriceSource ─┐
NewsSource ──┤→ SignalCollector(비순수: 타임아웃·캐시·fail-honest)
EarningsSrc ─┘        │ 순수 함수 호출:
                      ├─ detect_movers(rows, thr) ─→ [Mover]
                      ├─ build_readthrough([Mover], PeerMap, universe) ─→ [ReadThroughAlert]
                      ├─ select_imminent_earnings(cal, universe, held, horizon, PeerMap) ─→ [ImminentEarnings]
                      └─ assemble_brief(...) ─→ MarketSignalBrief
MarketSignalBrief ─→ prompts.morning_research_prompt(prepend)  [push]
                  └→ tools: movers / readthrough / earnings_calendar  [pull]
```
