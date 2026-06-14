# F81 — 13F 보유종목 시그널 소스 (요구사항)

## Intent Analysis
- **User request (원문)**: "우리 봇 포트폴리오에 자동으로 주기적으로 이걸 따와서 추가하도록 하자."
  - 대화 맥락에서 "이것" = **Leopold Aschenbrenner의 Situational Awareness LP**가 SEC에 제출하는
    **Form 13F-HR 공시 보유종목** (manager CIK `0002045724`).
- **Request type**: New Feature (신규 시그널/데이터 소스).
- **Scope**: Multiple Components — `src/signals/` (신규 소스), `src/universe/` (오버레이 병합), config.
- **Complexity**: Moderate — 외부 I/O(SEC EDGAR) + XML 파싱 + 분기 cadence + 방향성/숏 게이트 연동.
- **Depth**: Standard.

## 확정된 핵심 결정 (clarifying questions, 2 UAQ rounds)
| # | 질문 | 결정 |
|---|------|------|
| Q1 | "포트폴리오에 추가"의 의미 | **유니버스/워치리스트 확장** — 13F 종목을 봇이 스캔하는 tradeable 유니버스에 자동 편입. **자동 미러링/자동 매매 아님**. |
| Q2 | 대상 매니저 범위 | **설정 가능한 매니저 목록**, 1차 기본값 = Situational Awareness LP (CIK `0002045724`). 추후 CIK 추가만으로 확장. |
| Q3 | 데이터 소스 | **SEC EDGAR 직접** (13F-HR INFORMATION TABLE). 무료·공식. 서드파티 집계 사이트 사용 안 함. |
| Q4 | 방향성 처리 | **기존 숏 기능(F54/F60) 및 그 세팅과 comply.** (아래 FR-4 상세) |
| Q5 | 확장 규칙 | 명시 선택 없이 2회 비어 돌아옴 → 외부 I/O·파싱 비중 고려해 **둘 다 Enabled로 기본 제안** (승인 게이트에서 override 가능). |

## Functional Requirements

### FR-1. 일반 "공개 보유내역" 추상화 (소스-무관 계약) — 확장성의 핵심
> 사용자 피드백: 13F 전용으로 코드를 짜지 말고, 나중에 **다른 걸 plugin하기 쉬운 구조**로.
- `src/signals/holdings/` 신규 서브패키지에 **소스-무관 2층 추상화**를 둔다:
  - **정규화 레코드** (`records.py`): `HoldingsSnapshot{ source_id, as_of, rows[] }`,
    `HoldingRow{ ticker, side ∈ {LONG, SHORT}, weight, as_of, raw_meta }`.
  - **provider 프로토콜** (`provider.py`): `HoldingsProvider` — "공개된 보유내역 스냅샷을 낸다"는
    일반 계약. 13F는 그 **한 구현**일 뿐.
- **오버레이/브리프/방향게이트(FR-3·4·5)는 `HoldingsSnapshot`만 의존하고 13F를 모른다.**
  나중에 "다른 것"(다른 펀드 공시, 13D/G, 수동 리스트 등) 추가 = `HoldingsProvider` 구현 하나
  추가 + config `type` 등록. 오버레이/브리프 코드는 무변경.
- config는 **type-tagged provider 목록**: `signals.disclosed_holdings.providers: [{type, ...}, ...]`.
- **경계(YAGNI)**: 일반화 범위는 "공개 보유내역 → 방향 태그 → 유니버스/브리프"까지. "임의 데이터를
  유니버스에 꽂는 만능 소스"는 만들지 않음(기존 `src/signals/sources/` 가 이미 그 층의 플러그인).

### FR-2. SEC EDGAR 13F 구현 (`HoldingsProvider` 첫 구현)
- `src/signals/holdings/providers/sec_13f.py` — EDGAR 전용 fragile 로직을 **이 파일 안에만 격리**.
- 입력: provider config의 매니저 CIK. EDGAR submissions API
  (`https://data.sec.gov/submissions/CIK##########.json`)로 **최신 13F-HR(/A 수정본 포함)
  accession**을 찾고, 해당 filing의 **INFORMATION TABLE XML**을 파싱.
- 13F 원시 보유종목 → `HoldingRow` 정규화: `put_call=None`(주식)→`LONG`, `put_call=PUT`→`SHORT`,
  CUSIP→ticker 매핑, value/shares→weight.
- **CUSIP→ticker 매핑**: 13F는 CUSIP 기반, 봇은 ticker 기반. 매핑 성공분만 후보, 실패분은
  brief에 "unmapped N건"(드롭, fail-honest). 매핑 소스는 Application Design에서 확정
  (우선: 기존 유니버스/심볼 사전 재사용 → 보조 매핑).

### FR-8. 폼타입/스키마 변경 내성 (resilience) — 사용자 우려 직접 대응
> "13F-HR이 나중에 다른 걸로 교체돼 시스템이 망가질 가능성" 차단. 모두 **degrade(크래시 ❌)**:
- **수정본**: 최신 accession이 `13F-HR/A` 면 그걸 사용(원본만 찾지 않음).
- **13F-NT**(통지, 정보표 없음) / 정보표 부재: 파싱 시도 안 하고 해당 provider degrade.
- **매니저 신고 중단/말소**: 마지막 filing이 staleness 만료(FR-3) 넘으면 오버레이에서 드롭.
- **XML 스키마 drift**(v1/v2 네임스페이스 등): 관대한 파싱 + 실패 시 fail-closed degrade.
- **CIK 무효/오타**: 입력 검증으로 거부(Security Baseline).
- 최악의 경우라도 13F 섹션만 빠지고 유니버스는 **마지막 정상 스냅샷으로 폴백**하거나 비움.

### FR-7. 주기적 갱신 (cadence)
- 13F는 분기 공시 + 최대 45일 시차. 폴링은 **신규 filing 출현 감지** 목적.
- 기본 cadence: **하루 1회** 각 CIK의 EDGAR submissions를 확인, **새 13F-HR accession이
  감지되면** 보유종목을 다시 파싱하고 파생 오버레이를 갱신. (정확한 트리거 위치 — research turn
  진입 시 lazy refresh vs 별도 스케줄 — Application Design에서 확정.)
- 결과는 TTL 캐시(기존 collector 캐시 패턴 재사용) — push/pull 경로가 1회 수집 공유.

### FR-3. 유니버스 오버레이 편입
- 매핑된 13F **롱(주식) 보유종목**을 tradeable 유니버스에 **테마형 오버레이**로 병합
  (`src/universe/factory.py` `resolve_universe` 가 base ∪ themes 를 반환하는 기존 구조 활용).
- 오버레이는 **config 토글로 on/off** 가능, 매니저별로 켜고 끌 수 있음.
- **Staleness 처리**: 13F 오버레이는 최신 filing 기준으로 갱신되며, 설정된 만료(기본 ~135일,
  ≈ 한 분기 + 45일 시차)보다 오래된 filing만 있을 경우 오버레이에서 제외(또는 경고). 기본값은
  Functional Design에서 확정.

### FR-4. 방향성 + 숏 게이트 컴플라이언스 (Q4)
> SA LP의 13F는 **대부분 풋옵션(하락 베팅)**. 단순히 underlying을 롱 유니버스에 넣으면 방향 오인 발생.
- **롱(주식 SH) 보유** → 유니버스에 **롱 후보로 편입** (FR-3).
- **풋/숏-사이드 포지션** → underlying을 유니버스에 **숏 후보로 편입하되,
  `risk.shorting_enabled` 가 `true` 일 때만**. 기본(OFF)에서는 **brief의 '기관 하락 베팅'
  정보로만 노출**하고 tradeable 후보로 넣지 않음 (방향 오인·원치 않는 롱 진입 방지).
- 모든 숏 실행은 **기존 RiskManager 게이트(F54/F60: ETB/할트/필수 스톱)를 그대로 통과** —
  본 트랙은 **새 게이트를 만들지 않고 기존 게이트를 우회하지 않음**.
- 각 13F 종목은 brief/시그널에 **방향 태그(LONG / PUT·bearish)** 를 달아 에이전트가 절대
  풋을 강세로 오인하지 않게 함.

### FR-5. 리서치 브리프 노출
- 기존 `src/signals/brief.py` 의 push(프롬프트 prepend)/pull(on-demand tool) 경로에
  **13F 섹션** 추가: 매니저명·filing 분기·NEW/ADD/EXIT diff(가능하면)·방향 태그.
- 사람이 읽는 한 줄 요약 형태(기존 movers/earnings 섹션과 동일 톤).

### FR-6. Fail-honest 동작 (기존 NFR 패턴 준수)
- SEC fetch/파싱 실패는 **그 섹션만 degrade** (`degraded_sources` 기록), 리서치 턴을
  절대 크래시시키지 않음 — 기존 `SignalCollector` 의 fail-honest 계약과 동일.

## Non-Functional Requirements
- **NFR-1 (신뢰성/격리)**: 외부 소스 장애가 턴을 막지 않음 (FR-6).
- **NFR-2 (정합성)**: 순수 코어(파싱/diff/방향 분류) ↔ 불순 경계(HTTP) 분리 — 기존 signals 구조 준수.
  순수 코어는 단위/PBT 테스트 가능.
- **NFR-3 (성능)**: 13F는 분기 데이터 → 일 1회 폴링 + TTL 캐시로 충분. 턴 핫패스에 동기 네트워크 금지
  (캐시 미스 시에도 best-effort, 타임아웃).
- **NFR-4 (SEC 예의/ToS)**: SEC EDGAR fair-access 준수 — 식별 가능한 **User-Agent 헤더**,
  요청 rate 제한(≤10 req/s 권장), 호스트 핀(`data.sec.gov`/`www.sec.gov`) — SSRF 방지.
- **NFR-5 (설정 안전 기본값)**: 매니저 목록·오버레이·숏-사이드 편입 모두 config 토글. 숏-사이드는
  `shorting_enabled` 에 종속 → **기본 long-only 안전**.

## 통합 지점 (brownfield)
- **`src/signals/holdings/`** (신규 서브패키지) — `records.py`(HoldingsSnapshot/HoldingRow),
  `provider.py`(HoldingsProvider 프로토콜), `providers/sec_13f.py`(EDGAR 구현), `overlay.py`.
- `src/signals/collector.py`, `brief.py`, `records.py`, `settings.py` — holdings 섹션 배선
  (소스-무관: `HoldingsSnapshot` 소비).
- `src/universe/factory.py` (+ provider) — `resolve_universe` 오버레이 병합 지점.
- `config/settings.yaml` — `signals.disclosed_holdings.providers: [{type, ...}]`
  (type-tagged; 1차 `{type: sec_13f, cik, overlay}`) + staleness/cadence 토글.
- 숏 연동: `src/risk/manager.py` 게이트는 **변경 없이** 그대로 사용.

## Out of Scope (명시)
- 13F 비중 **자동 미러링/자동 주문**(Q1에서 명시적으로 배제).
- 옵션 자체 거래(풋 매수 복제) — 봇은 주식/숏만, 옵션 미러 불가.
- 서드파티 집계 사이트 스크래핑(Q3에서 배제).
- 13F 외 공시(13D/G, Form 4 등) — 본 트랙엔 미포함이나, **FR-1 추상화 덕에 후속 트랙에서
  `HoldingsProvider` 구현 추가만으로 plugin 가능**(오버레이/브리프 무변경).
- "임의 데이터를 유니버스에 꽂는 만능 소스" — FR-1 YAGNI 경계 밖(과설계 방지).

## Extension Configuration (제안 — 승인 게이트에서 확정)
| Extension | 제안 | 근거 |
|---|---|---|
| Security Baseline | **Enabled** | 외부 SEC HTTP fetch + XML 파싱 + config CIK 입력 → 입력검증·호스트핀(SSRF 방지)·fail-closed 파싱이 실제 적용 대상. |
| Property-Based Testing | **Enabled (pure-functions/round-trip)** | XML 파싱·보유종목 diff·CUSIP/ticker 정규화 등 순수 로직의 불변식/라운드트립 검증에 적합. |

## 관련
- [[f61-market-signals]] (시그널 소스-플러그인 패턴/구조), F54·F60 (숏 기능/게이트), F77 (소스 추가 선례).
