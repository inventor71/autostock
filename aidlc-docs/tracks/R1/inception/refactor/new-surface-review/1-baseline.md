# Stage 1 — Baseline: 신규 표면 정밀 리뷰 (new-surface-review)

**작성일**: 2026-05-31
**범위**: F1–F8로 추가된, 2026-05-28 구조 리뷰(`code-quality-assessment.md`, U1–U7) **이후의 미검토 표면**
- `src/agent/steering/` (10 파일, ~1,700 LOC)
- `src/agent/intraday/` (12 파일)
- `src/strategy/llm/` (6 파일)
- `src/data/intraday_*.py` (collector/store/features/analysis)
- `operator-console/launcher/*.ts` (프로젝트 작성 TS, 710 LOC)

**범위 밖 (명시)**: `operator-console/cli/` 본체 = vendored opencode 포크(packages/ 5093 파일, 번역 README, `patches/`=upstream 의존성 패치). 우리 코드 아님 → 리팩토링 대상 아님.

**사용자 결정**: 4개 관심사(중복/과한주석/속도/보안) 중 **"신규 표면 정밀 리뷰"** 범위만 진행. 다른 트랙(소수 실제 항목 / deferred Q·H 청산 / 진행 안 함)은 선택 안 됨.

---

## A. 전체 건강도 (정직한 평가)

신규 표면도 **원래 코어와 동일하게 잘 설계되어 있다.**
- 공유 유틸이 이미 올바르게 분리됨: `steering/jsonl.py`(torn-safe read + atomic write + OffsetCursor)를 channel/news_diff/journal이 재사용. `core/trades.py::match_round_trips`를 라이브 원장과 backtest가 공유. `intraday/bars.py::atr/avg_volume`가 단일 출처.
- 보안이 **defense-in-depth**: PreToolUse deny-hook(`steering/security.py`)로 에이전트 파일 권한을 workspace 밖으로 못 나가게 차단, operator token은 daemon이 발급→env로 전달→에이전트 spawn 전 scrub(메모리/로그 비노출), 로그 secret 마스킹(`runtime.py`), subprocess는 전부 arg-array(`shell=True` 없음), launcher는 SECURITY-03로 토큰 값 대신 boolean만 노출.
- `except Exception`이 49곳이지만 대부분 **의도된 fail-closed / "워커 스레드를 절대 죽이지 않는다"(BR-8.2)** 패턴 + 로깅 동반 → 트레이딩 데몬에 적절. 삼키는 스멜 아님.

→ **결론: 명명된 3개 관심사("중복/과한주석/속도")는 신규 표면에서도 대부분 부재.** 실제 항목은 소수이며 저-ROI. 아래 후보를 Stage 2 ledger에서 tier 분류한다.

### 과한 주석 — 실측으로 부재 (조치 없음)
Python 주석 비율 최대 13%(`journal.py`), 신규 표면 상위(`agent.py` 12%, `session.py` 11%, `runtime.py` 9%)도 모두 건강 범위. 내용은 BR/불변식 인용(예: `gate.py`의 BR-4.6 보호주문 예외, `security.py`의 권한분리 근거) = **고가치**. 제거 시 유지보수성 하락 → **리팩토링 대상에서 명시적으로 제외.**

---

## B. 보존해야 할 관측 가능 동작 (외부 계약)

리팩토링 중 **반드시 불변**으로 유지할 것:

1. **주문 경로 단일 게이트**: 인간/에이전트 트레이드 모두 `executor.execute_decision` → `RiskManager` 브라켓 → `Broker`(BR-2.1). SELL은 RiskManager가 사이징, BUY는 `build_human_buy`(명시 size + 보호 브라켓). 부수효과(실주문) 동일.
2. **steering 파일 채널 프로토콜**: `steering/commands.jsonl`(operator→daemon, confirmed+token), `snapshot.json`(daemon→operator atomic), 오프아워 큐 드레인(BR-2.7), corr_id 멱등/dedup(BR-11.2), bad-token fail-closed.
3. **권한 분리 계약**: deny-hook가 workspace 밖 경로 차단(exit 2), token scrub. 시그니처 `evaluate()/path_is_inside()/scrub_agent_env()` 동작 동일.
4. **approval gate**: 인간-locked 심볼의 에이전트 BUY/SELL는 park, denied는 auto-reject, 보호주문/risk-exit는 면제(BR-4.6).
5. **intraday 계약**: `watch.jsonl` 단일 writer(에이전트 tool, BR-6.1), wake/brief 트리거 임계(ATR k배 등), 5분봉 출처.
6. **LLM 컨텍스트 출력 포맷**: `MarketDataFormatter.format_for_llm`의 섹션 구조/헤더 문자열(프롬프트 계약). `truncate_context` 경계 동작.
7. **launcher CLI 계약**: `autostock`/`autostockd` 동작, systemd unit ExecStart, preflight 체크 id, 토큰 비노출.

---

## C. 특성화(characterization) 테스트 현황

| 영역 | 기존 커버리지 | 공백 |
|------|---------------|------|
| `steering/` | **강함** — `test_steering_{bus,channel,commands,contract,gate,records,runtime,security,state,turns}.py` (10) | 없음 (대부분 경로 덮음) |
| `intraday/` | **강함** — `test_intraday_*` (12) | 없음 |
| `strategy/llm/` | **없음** — formatter/client/prompt_manager 직접 테스트 0 (기존 Q-4에서 LLM 커버리지 공백 지적됨) | **데이터 포맷터 출력 고정 테스트 필요** |
| `launcher/*.ts` | `contract`/`preflight`/`daemon` bun 테스트 존재(포크 내) | 부분 |

→ **특성화-우선 규칙 적용**: `strategy/llm/` 변경 항목은 Stage 4 진입 전, `format_for_llm` 출력을 고정하는 특성화 테스트를 **먼저 추가**해야 한다(현재 "옳다"가 아니라 "현재 이렇다"를 캡처).

---

## D. 발견된 실제 후보 (Stage 2에서 tier 분류 예정)

> 잠정 tier만 표기. 확정은 `2-tier-ledger.md`에서.

| ID | 항목 | 파일:라인 | 관심사 | 잠정 tier |
|----|------|-----------|--------|-----------|
| N-1 | `_find_resistance_levels`/`_find_support_levels` 거울상 중복 → 방향 파라미터 1개 헬퍼로 통합 | `data_formatter.py:266-294` | 중복 | T1 (단, 특성화 테스트 선행) |
| N-2 | 함수내 lazy import 다수(`modes/agent._setup_intraday` 등 ~20곳) 중 **상수 비용/필수 의존성 아닌 것** 일부를 모듈 top으로 | `modes/agent.py:62-103`, `data_formatter`(N/A) 등 | 속도/명료성 | T1 (site별 판단; torch/alpaca-live/optional은 유지) |
| N-3 | 스테일 모델 id 기본값 `claude-sonnet-4-20250514`, `gpt-4o` (config null→이 fallback) | `strategy/llm/client.py:82,116` | 보안/정확성(staleness) | **T3** (기본 모델 교체=출력 변경; provider 경로 동작 바뀜 → 승인 필요) |
| N-4 | `rf_strategy`의 `pickle.load`(모델 역직렬화) 신뢰경계 주석/검증 | `strategy/ml/rf_strategy.py:92` | 보안 | T1/노트 (자체 생성 모델 → 저위험; 경고 주석 + 경로 검증만) |
| N-5 | `ClaudeClient.complete` prompt caching 부재(반복 system prompt) | `strategy/llm/client.py:88-108` | 속도/비용 | T2 (additive; 출력 동일) — 단 비기본 경로라 저우선 |
| N-6 | `commands.build_human_buy`가 `risk_manager._resolve_stop`(private) 호출 | `commands.py:53` | 결합도 | T1 (public 위임 메서드로) — 사소 |

**주의**: N-3는 "기본 모델 교체"이므로 동작/출력 변경 → **T3 게이트**. 자동 적용 금지, Stage 2에서 사용자 승인 안건으로 제시.

---

## E. Stage 1 판정

- 신규 표면은 건강하며 **큰 리팩토링 불필요**. 실제 항목은 N-1~N-6(대부분 T1·사소, 1건 T3, 1건 T2 저우선).
- "과한 주석"은 부재 → 조치 제외.
- 다음 단계(Stage 2)에서 N-1~N-6을 tier ledger로 확정하고, 각 T1 항목을 특성화 테스트에 매핑(특히 `strategy/llm/`은 테스트 선행). N-3(T3)은 사용자 승인 안건으로 정지 제시.
