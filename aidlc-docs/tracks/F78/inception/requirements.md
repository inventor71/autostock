# F78 — 이벤트-레이더 (Tier1, 인지 전용) · 요구사항

**Depth**: standard · **Phase**: INCEPTION / Requirements Analysis
**Date**: 2026-06-13 · **Base**: bacd341

## 1. 배경 / 문제
research 턴의 시장 인지는 `src/signals/`의 세 채널(movers / read-through / earnings)뿐이고,
**셋 다 심볼(티커) 키 기반에 고정 universe 위에서만** 작동한다. 따라서 IPO·M&A·규제·매크로처럼
**아직 티커로 역인덱싱되지 않는 이벤트**(예: SpaceX `SPCX` 상장)에는 구조적으로 둔감하다.
에이전트는 `WebSearch`/`WebFetch`를 *이미* 보유(`session.py:79-80`)하나, (a) top-down으로
이벤트를 훑으라는 **지시**가 없고 (b) Discovery는 scoreboard(=universe)에 고정돼 출발점이 없다.

## 2. 목표 / 비목표
**목표 (Tier1 = 인지)**: 임박 IPO를 결정론적으로 brief에 push하고, Regime 단계에서 매크로/이벤트
촉매를 top-down으로 보게 만들어 **블라인드사이드를 막고 보유·universe로의 read-through를 읽게** 한다.

**비목표 (명시)**:
- universe 동적 승급(Tier2) — 별도 결정.
- **day-1 IPO 직접 매수** — 가격 이력이 없어 이 시스템의 ATR/RSI 기반 손절 프레임이 작동 불가.
- MCP 리팩토링 — 별도 병렬 트랙(F79 예정).
- Discovery(step 4) 주입 — "메뉴 고르기" 단계라 의미·리스크 부적합. 인지는 Regime(step 2)에.

## 3. 기능 요구사항 (FR)

### FR-1 — Finnhub IPO 캘린더 소스 (Push 데이터)
- 신규 provider `src/signals/sources/finnhub_ipo.py` 추가. 기존 `finnhub_earnings.py` 패턴 병렬
  (`/calendar/ipo` 엔드포인트, 단일 HTTP 호출, `FINNHUB_API_KEY` 재사용).
- 날짜 범위(`from`~`to`) 질의 → IPO 행 리스트 반환. 전송/HTTP 오류는 **raise**(수집기가 degrade).
- 결정론·방어적 파싱: 누락 필드 행은 skip, 위조 데이터 생성 금지(fail-honest).

### FR-2 — 선별 로직 (pure core)
- **임박 US IPO 전부**: `today` ~ `today + horizon_days` 범위 내 상장 예정 IPO.
- 정렬: 규모 desc(가용 시 공모액/예상시총; 없으면 안정 정렬 fallback) → **상한 캡**(`max_ipos`).
- pure: 같은 입력 → 같은 출력. 거래소 필터(US) 적용. (PBT 대상)

### FR-3 — SignalCollector 통합
- `SignalCollector.collect()`에서 earnings와 **나란히** IPO 캘린더 수집(`collector.py:118` 인근).
- best-effort + fail-honest: 실패 시 `degraded_sources`에 기록, research 턴은 절대 크래시 안 함.
- 기존 **TTL 캐시 공유**(push/pull 1회 collect). horizon override는 cache-key에 반영.

### FR-4 — Brief 섹션 (Push 렌더)
- `MarketSignalBrief`에 IPO 필드 추가, `assemble_brief()`는 순수 번들링 유지.
- `to_prompt_text()`에 **"Imminent IPOs / catalysts"** 섹션 추가(earnings 블록 다음). 비면 생략.
- 행 표기: 심볼(있으면)·회사명·상장예정일·거래소·규모(가용 시). universe/보유 연관 태그.

### FR-5 — Regime nudge (Prompt)
- `morning_research_prompt`의 **step 2 (Regime)**에 additive 한 줄: "brief의 IPO 캘린더 +
  매크로/이벤트 촉매(M&A·규제·매크로)를 web research로 top-down 스캔하고, 섹터/심리 영향과
  보유·universe 종목으로의 read-through를 regime.md에 기록." (Discovery 미변경)
- 매크로 촉매는 **prompt-only**(신규 데이터 소스 없음; 기존 WebSearch/WebFetch 활용).

### FR-6 — Pull 도구 parity
- `python -m src.agent.tools ipo_calendar [--days N]` CLI 서브커맨드 추가(earnings_calendar 대칭).
- 프롬프트 도구 가이드(`_SIGNAL_TOOL_GUIDE`, `prompts.py:183~`)에 ipo_calendar 항목 추가.

### FR-7 — 설정 (config-driven)
- `SignalsConfig`에 IPO 관련 키 추가: `ipo_horizon_days`(기본값), `max_ipos`(캡),
  소스 토글(`SignalSources`에 `ipo_provider: "finnhub" | "none"`). 코드에 임계값 하드코딩 금지.

## 4. 비기능 요구사항 (NFR)
- **NFR-1 (fail-honest)**: 어떤 소스 실패도 research 턴을 크래시시키지 않음 — degrade만.
- **NFR-2 (latency/timeout 보존, 하드)**: IPO HTTP 호출은 기존 session-timeout helper로 바운딩.
  research 턴 지연 예산 침해 금지.
- **NFR-3 (cache)**: push(prompt)·pull(tools) 경로가 단일 collect 공유(TTL).
- **NFR-4 (eval seam 보존, 하드)**: F74 fixture 가로채기(`AUTOSTOCK_TOOLS_FIXTURE_DIR`, CLI
  dispatch)가 `ipo_calendar`에도 동일 적용 — eval 턴은 라이브 데이터 미접촉.
- **NFR-5 (security baseline)**: API 키 env-only, 로그/예외에 키 비노출, 외부 응답 방어적 파싱.

## 5. 인수 기준 (Acceptance)
1. `FINNHUB_API_KEY` 부재/HTTP 실패 시 brief의 다른 섹션은 정상, IPO만 degraded로 누락.
2. 임박 IPO가 있으면 brief에 "Imminent IPOs / catalysts" 섹션이 규모순·캡 적용되어 렌더.
3. `ipo_calendar` CLI가 earnings_calendar와 대칭으로 동작, fixture 모드에서 라이브 미접촉.
4. Regime nudge가 research 프롬프트 step 2에 존재(Discovery 미변경).
5. 선별 pure core에 PBT(정렬·캡·horizon 경계·멱등) + record 직렬화 라운드트립 통과.
6. 기존 F61 signals 동작·테스트 회귀 없음.

## 6. 가정 / 기본값 (합리적 디폴트로 진행)
- `ipo_horizon_days` 기본 = earnings와 정합되게 작게(예: 3~5일) — 설계 단계에서 확정.
- `max_ipos` 캡 = 한 자릿수(예: 8) — brief 비대화 방지.
- Finnhub free tier `/calendar/ipo` 필드(symbol/name/date/exchange/numberOfShares/price/
  totalSharesValue)를 규모 근사로 사용. 필드 부재 시 규모 미상 → 정렬 후순위, 행은 유지.
- 미국 거래소 한정(에이전트 거래 가능 시장과 정합).

## 7. Extension 준수 요약
- **Security Baseline (Enabled)**: 적용 = API 키 env-only·비노출, 외부 응답 신뢰경계 방어 파싱,
  fail-honest. N/A = 인증/인가·세션·주문 경로·사용자 입력 없음(read-only 수집).
- **Property-Based Testing (Partial)**: 대상 = 선별 pure core + record 직렬화. 비대상 = I/O
  경계 수집기·프롬프트 텍스트(예제 기반).
