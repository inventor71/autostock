# F95 — Symbol 클릭 → 주요 정보 Floating Panel · Requirements

> Track F95 · Requirements Analysis (Standard depth). 단일 작성자 = F95 worktree 세션.
> 관련 메모리: [[opentui-zorder-hittest]] (TUI hit-test), [[kis-api-facts]], [[account-farm-sdk-schema-drift]].

## 1. Intent Analysis (요약)

| 항목 | 값 |
|---|---|
| **User Request (원문)** | "autostock에서 symbol을 누르면 주요 정보를 floating panel로 띄우는걸 하면 좋겠어." |
| **Request Type** | Enhancement (기존 SymbolOverlay 패널 활용) + 신규 데이터 채널 |
| **Scope** | Multiple Components — TUI 렌더 계층(`operator-console/cli`) + 데몬(Python `src/`) 간 신규 시세 경로 |
| **Complexity** | Moderate — UI 변경은 작지만, TUI(file-only)↔데몬 실시간 시세 채널이 신규 |
| **Target Surface** | **TUI 운영자 콘솔** (opentui) — 확정 |

### 핵심 발견 (feasibility 조사 결과)
- 플로팅 패널(`SymbolOverlay` + `OverlayPanel`)과 `overlay.openSymbol(sym,x,y)`는 **이미 구현되어 있음**. 오늘은 **turn 오버레이 안의 심볼만** 클릭 가능(`turn-overlay.tsx:91`).
- 채팅 심볼 클릭 = **HARD** (채팅 텍스트가 opaque native `<markdown>` 렌더러로 그려짐, per-token 노드/클릭 API 없음) → **이번 트랙 범위 밖**(별도 후속).
- 타임라인/기존 base 화면엔 클릭할 **종목 텍스트가 사실상 없음**(글리프만). 유일한 신규 UI 진입점 = **intervention 오버레이 심볼**(`intervention-overlay.tsx:32`, 현재 비클릭).
- TUI는 **파일 전용**(데몬으로의 request 채널 없음). MCP quote 툴은 **stdio 벽** 뒤(LLM 에이전트 서브프로세스) → TUI 렌더 계층에서 호출 불가. 임의 종목 실시간 시세는 **신규 플러밍 필요**.

## 2. 확정된 스코프 결정 (사용자 답변)

| 결정 | 값 | 근거 |
|---|---|---|
| 대상 화면 | TUI 콘솔 | 패널 90% 기구축, 파일주도 아키텍처 |
| 클릭 진입점 | **intervention 오버레이 심볼만** 신규 클릭화 (turn 오버레이는 이미 동작) | "최소" 선택 — 최소 UI 변경 |
| 시세 범위 | **임의 종목 실시간 시세** | 미보유 종목 포함 항상 표시 원함 |
| 패널 콘텐츠 우선순위 | **시세 = 항상 표시(필수)** / 현행(포지션·thesis·결정) = 있으면 표시, 없으면 생략 | 사용자 정정 (2026-07-06T16:08Z) |

## 3. Functional Requirements

### FR-1 — Intervention 오버레이 심볼 클릭 (신규 진입점)
- intervention 오버레이에 렌더되는 종목(`intervention-overlay.tsx:32`)을 **클릭 가능**하게 만든다.
- 클릭 시 기존 `overlay.openSymbol(symbol, x, y)`를 호출해 **SymbolOverlay 플로팅 패널**을 연다 (turn 오버레이의 `onMouseUp` 패턴과 동일 — `turn-overlay.tsx:91-97`).
- turn 오버레이 심볼 클릭은 **현행 동작 유지**(회귀 없음).

### FR-2 — 실시간 시세: 항상 표시 (패널 핵심 요소) · **클릭 즉시 + ~1-2s 신선도**
- SymbolOverlay는 클릭된 **모든** 심볼에 대해 시세를 표시한다. **미보유 종목도 포함**.
- **반응성 목표(사용자 확정)**: 클릭 시점에 시세가 **즉시** 뜬다(디스크 warm 값 읽기, 왕복 없음). warm-cache **갱신 주기 ~1-2s**.
- 표시 항목(최소): 최신가(latest/last). 가능하면 일중 등락(전일 종가 대비)·시각. 구체 필드셋은 Functional Design.
- **데이터 경로(신규) — per-instance REST 워밍 캐시** (아키텍처 결정 근거는 §9):
  1. 데몬이 **클릭-후보 심볼 집합**(보유 ∪ 미체결 주문 ∪ 최근 turn/decision/intervention 등장 심볼 [∪ watchlist])을 계산.
  2. 데몬의 slow-cadence 워커가 그 집합을 **~1-2s마다 배치 REST**(`fetch_latest_prices(data_provider, symbols)` — `src/data/prices.py`)로 갱신해 **원자적으로 warm-cache**(인스턴스 steering 경로, ts+TTL, 기존 `_price_book` 패턴 — `runtime.py:178,435-463`)에 기록. **지속 websocket 연결 없음** → 연결 한도/공유 볼륨 문제 원천 배제.
  3. TUI는 클릭 시 해당 심볼을 warm-cache에서 **즉시 읽어** 표시(+ "as of HH:MM:SS" 신선도). 짧은 폴링으로 갱신 반영.
- **Fast-path**: 클릭 심볼이 이미 `snapshot.json`에 있으면(보유·주문) `current_price`를 즉시 사용.
- **캐시 미스 폴백**: 후보 집합 밖 심볼(드묾 — 클릭 대상은 대개 agent 처리 종목) 클릭 시 → 온클릭 1회 fetch로 채우고 도착 전 "조회 중". (온클릭 요청 채널은 설계에서 필요성 판단; 후보 집합에 클릭 심볼 즉시 편입도 대안.)
- **provider 정직성**: 시세의 real-time성은 인스턴스의 `settings.data.provider`에 의존 — Alpaca 데이터 키=실시간, **yfinance(기본)=지연 가능**. 캐시 갱신 주기(~1-2s)와 데이터 지연은 별개 → 패널은 "as of" 시각으로 정직 표기(허위 실시간 주장 금지).
- **로딩/실패 처리**: 시세는 필수 요소 — 조용히 생략하지 않는다. 도착 전 로딩, 조회 불가(키 부재/provider 오류/심볼 오류) 시 "시세 없음/오류"를 신선도와 함께 명시.

### FR-3 — 현행(보유·thesis·결정): 있으면 표시, 없으면 생략
- 다음 3종은 **가용할 때만** 표시하고, 없으면 **조용히 생략**(빈 섹션 노출 금지):
  - 포지션: 수량/진입가/현재가/평가손익 (`snapshot.json` positions — `use-snapshot-data.ts`).
  - Thesis: `workspace/positions/<SYMBOL>.md` (`use-thesis.ts`, path-traversal 가드 유지).
  - 최근 결정/액션: monitor `decisions`에서 해당 심볼 필터(`symbol-overlay.tsx:26-29`).
- 미보유·thesis 없음·결정 없음 종목이라도 **패널은 열리고 시세는 표시**된다(FR-2).

### FR-4 — 패널 상호작용 (기존 OverlayPanel 동작 계승)
- 앵커(클릭 x/y) 위치에 뜨고, 터미널 경계로 자동 클램프(`overlay-panel.tsx:18-30`).
- **바깥 클릭 시 닫힘**(백드롭 `onMouseUp` — `overlay-panel.tsx:38-41`). 같은 심볼 재클릭 토글(`use-overlay.ts:23`) 동작 유지.
- z-order/hit-test는 기존 규약 준수 — [[opentui-zorder-hittest]].

## 4. Non-Functional Requirements

- **NFR-1 (아키텍처 정합)**: TUI는 파일 전용 원칙 유지. warm-cache 경로는 기존 steering 파일채널 패턴(원자적 write, torn-read 방지, 단일 writer)을 따른다. TUI 렌더 계층에서 데몬 동기 RPC 금지. 시세 갱신 워커는 단일 CommandBus/데이터 접근 규약과 정합(별도 slow-cadence 잡, 기존 `_price_book` 슬로우 잡과 동류).
- **NFR-2 (반응성/신선도)**: 클릭 즉시 표시(warm-cache 파일 읽기). warm-cache 갱신 주기 = **~1-2s**. 캐시 미스 온클릭 폴백은 1회 fetch, 도착 전 로딩. TUI 폴링은 렌더를 블로킹하지 않음.
- **NFR-3 (멀티 인스턴스 격리 — 문제 원천 배제)**: warm-cache 파일은 인스턴스별 steering 경로 격리(F90/F92 준수). **지속 websocket 연결이 없으므로** Alpaca 1-연결 한도/공유 볼륨/사이드카 이슈가 **발생하지 않음**. 각 인스턴스는 자기 candidate 집합만 REST 폴링(브로커 무관, account_farm 포함 동일).
- **NFR-4 (Fail-honest — 진짜 장애만)**: 데이터 provider 조회 불가(키 부재/네트워크/심볼 오류) 시 패널에 "시세 없음/오류" + 신선도. 데몬 크래시 금지 — [[account-farm-sdk-schema-drift]]. (연결-한도 강등 같은 우회 용도 아님.)
- **NFR-5 (회귀 없음)**: 기존 turn/SymbolOverlay·다른 오버레이(health/intervention) 회귀 금지. 시세 기능은 기능 플래그/파일 부재 시 비활성해도 패널·기존 동작 무영향.
- **NFR-6 (레이트리밋/부하)**: candidate 집합만 배치(`fetch_latest_prices`, 동시성) + ~1-2s 주기 + 단기 캐시로 provider 레이트리밋 보호. yfinance 기본은 지연·간헐 실패 가능 → 백오프/graceful.

## 5. User Scenarios

1. **미보유 종목 클릭**: 운영자가 intervention 오버레이에서 미보유 심볼(예: 에이전트가 검토한 종목)을 클릭 → 패널이 열리고 **실시간 시세 표시**, 포지션/thesis/결정 섹션은 없으므로 생략.
2. **보유 종목 클릭**: 보유 심볼 클릭 → 시세(스냅샷 즉시가 또는 라이브) + 포지션(수량/진입/PnL) + thesis + 최근 결정 모두 표시.
3. **시세 조회 실패**: 시장데이터 키 없음/장외/심볼 오류 → 패널은 열리되 "시세 없음/오류" 명시(조용한 실패 아님).
4. **바깥 클릭**: 패널 바깥 클릭 시 닫힘. 같은 심볼 재클릭 토글.

## 6. Out of Scope (이번 트랙 아님)

- **채팅 심볼 클릭 링크화** (HARD — opaque native markdown 렌더러). 별도 후속 트랙/스파이크로 분리.
- **초이하 스트리밍(공유 사이드카)** — 멀티 인스턴스에서 초이하 신선도가 필요해질 때의 후속 옵션(§9-B). 이번 트랙은 ~1-2s REST 워밍캐시로 확정.
- 모바일 PWA / viz-shell 의 symbol 상호작용(각각 F79/F86, F73 계열). 참고용 prior art일 뿐 이번 delivery surface 아님.
- 신규 상시 포지션/워치리스트 리스트 UI(사용자가 "최소" 선택으로 제외).
- 타임라인 글리프의 티커화.

## 7. Extension Compliance
| Extension | Enabled | Rationale |
|---|---|---|
| Security Baseline | No (opt-out) | 읽기 전용 TUI 조회 기능, 외부 입력 없음. 단, path-traversal 가드(thesis)·인스턴스 격리는 기존 규약으로 유지. |
| Property-Based Testing | No (opt-out) | UI/데이터 배선 위주, 복잡 알고리즘 없음. 파서(있다면)는 일반 단위테스트로 커버. |

## 8. Key Requirements 요약
- **핵심 신규 UI**: intervention 오버레이 심볼 클릭 1건(나머지 진입점은 이미 존재).
- **핵심 신규 백엔드**: candidate 종목 시세를 ~1-2s 배치 REST로 갱신하는 **per-instance 데몬 warm-cache** + TUI 리더 (이 트랙의 실질 엔지니어링 무게중심).
- **패널 콘텐츠 규칙**: 시세=항상 / 현행(포지션·thesis·결정)=있으면.
- **비회귀·격리·fail-honest** 필수.

## 9. 아키텍처 결정 (ADR) — 시세 플레인

**맥락**: TUI는 파일 전용(데몬 RPC 없음). 시세 데이터 provider는 트레이딩 브로커와 분리된 **계정-무관 전역 플레인**(`create_data_provider`, `main.py:15-34`) — account_farm/broker_api 인스턴스도 시세는 브로커 API가 아니라 이 provider에서 받음. prod 기본 provider=yfinance(스트리밍 없음), Alpaca 스트리밍은 별도 데이터 키 필요·prod 미배선. F90 prod=인스턴스별 격리 컨테이너(격리 볼륨).

**검토한 대안**:
- **(A) per-instance REST 워밍캐시 (채택)** — 각 데몬이 자기 candidate 집합을 ~1-2s 배치 REST로 갱신→자기 steering warm-cache. 지속 연결 없음 → websocket 1-연결 한도·공유 볼륨·사이드카 **문제 원천 배제**. 인프라 0, yfinance/Alpaca 무관, 브로커 무관(account_farm 동일). 신선도 ~1-2s(초이하 아님).
- **(B) 공유 스트리밍 사이드카** — 단일 websocket이 심볼 union 구독→공유 read-only 볼륨→전 인스턴스 읽기. 초이하·멀티인스턴스 정답이나 신규 인프라(사이드카+compose+전용 Alpaca 데이터 키+union 조율). **후속 옵션으로 보류**(§6 Out of Scope).
- **(C) 단일 인스턴스 스트리밍** — 사이드카 없이 데몬 직접 스트림. 단일 운영 시 초이하·최소인프라지만 N개 동시+키공유 시 충돌(문제 이연). 미채택.

**결정**: **(A)**. 근거 — "클릭 즉시"는 세 안 모두 동일(warm-cache 읽기), 정보 패널 용도엔 ~1-2s 신선도로 충분하며, 사용자가 제기한 멀티 인스턴스(broker_api 포함) 연결-한도 문제를 **회피가 아니라 구조적으로 제거**. 초이하가 필요해지면 (B)로 확장.

**폐기된 접근**: "per-instance 스트리밍 + fail-honest 강등" — fail-honest가 연결-한도의 해결책이 아니라 기능 취지를 훼손하는 강등이라는 사용자 지적으로 폐기.
