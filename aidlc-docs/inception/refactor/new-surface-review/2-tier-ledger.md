# Tier Ledger — new-surface-review

범위: F1–F8 신규 표면 (`src/agent/steering/`, `src/agent/intraday/`, `src/strategy/llm/`, `src/data/intraday_*`, `operator-console/launcher/*.ts`)
작성일: 2026-05-31
기준 baseline: `1-baseline.md`

> 원칙: 분류 애매하면 더 높은 tier로(보수적). T1/T2 각 항목은 보호하는 특성화 테스트에 매핑한다.
> 보호 테스트가 없으면 단계 1로 돌아가 테스트를 먼저 추가한 뒤 진행.

---

## T1 — 동작 보존 (자율 진행)

| # | 변경 항목 | 보존되는 동작 | 보존 검증 방식 | 근거 |
|---|-----------|---------------|----------------|------|
| **N-1** | `data_formatter._find_resistance_levels`/`_find_support_levels` 거울상 중복을 방향 파라미터 1개의 헬퍼(`_find_pivot_levels(bars, current, direction)`)로 통합. 두 public-facing 호출부는 thin wrapper 유지. | `format_for_llm` 출력 문자열 **완전 동일** (Recent Highs/Lows 라인 포함). 정렬 순서(저항=오름, 지지=내림) 동일. | ⚠️ **특성화 테스트 필요** — `strategy/llm/` 직접 테스트 0개. 단계 4 진입 전 `tests/test_llm_formatter.py` 신규 작성(고정 OHLCV → `format_for_llm`/`_find_*_levels` 출력 스냅샷). | 거울상 로직 → pivot-detection 1곳. 출력 계약은 baseline §B-6. |
| **N-4** | `rf_strategy`의 `pickle.load`에 신뢰경계 경고 주석 + 모델 경로가 설정된 모델 디렉터리 안인지 검증(path containment, `steering/security.path_is_inside` 패턴 재사용). | 정상 경로(자체 생성 모델 로드) 동작 동일. 잘못된 경로만 fail-closed. | 기존 `test_strategies.py`의 rf 로드 경로 + 1 신규 테스트(디렉터리 밖 경로 거부). | 자체 생성 모델 → 저위험이나, 임의 경로 역직렬화 표면 축소(SECURITY 방어). |
| **N-6** | `commands.build_human_buy`의 `risk_manager._resolve_stop(...)`(private) 호출을 public 위임 메서드 `RiskManager.resolve_stop(...)`로 교체(thin wrapper 추가, private는 내부 유지). | 인간 BUY 주문 산출(qty/stop/target) **완전 동일**. | 기존 `test_steering_commands.py`(human-buy 경로) + `test_risk.py`. | 결합도 사소 개선. cosmetic — 저우선. |
| **N-7** ✅ | **F6 tsgo 타입 에러 2건 수정**(콘솔 포크): `<box selectable={false}>`(home.tsx:124, sidebar.tsx:55)가 `BoxProps`에 없는 prop이라 `error TS2322`. `@opentui/core 0.2.16`이 `selectable`을 `TextBufferOptions`엔 두고 `BoxOptions`엔 누락(런타임 `Renderable.selectable`은 존재). → 타입 전용 module augmentation `src/opentui-box-selectable.d.ts`로 `BoxOptions.selectable?: boolean` 추가. | **런타임 동작 0 변경**(타입만). 드래그 핸들 selectable=false 동작 그대로. | `bun run typecheck`(tsgo): 2 errors → **0**. 시각 동작은 기존 F6 라이브검증으로 커버. | 사용자 직접 제기("이거도 같이 확인"). 우리 작성 F6 코드의 lib 타입 상호작용 결함. **이미 working tree에 적용+검증 완료**(submodule, 미커밋). |

## T2 — 안전한 확장 (자율 진행 + 사후 보고)

| # | 추가 항목 | 기존 동작 영향 | 보존 검증 방식 | 비고 |
|---|-----------|----------------|----------------|------|
| **N-5** | `ClaudeClient.complete`에 prompt caching(`cache_control`) 추가 — 반복되는 system prompt 캐싱. | 없음(superset; 응답 텍스트 동일, 비용/지연만 감소). | 신규 `test_llm_formatter.py`와 별개로 client 호출 인자 단위 테스트 1개(캐시 헤더 첨부 확인, 응답 파싱 불변). | **저우선** — `claude` provider는 프로젝트 기본 경로 아님(기본=`claude_code` subprocess). ROI 낮음. 사후 보고. |

## T3 — 의도 변경 / 기능 cut (🛑 승인 필요)

| # | cut/변경 내용 | 이유(복잡도 비용) | 얻는 것 | 잃는 것 | 영향 범위 | 사용자 결정 |
|---|---------------|-------------------|---------|---------|-----------|-------------|
| **N-3** | 스테일 기본 모델 id 교체: `ClaudeClient.default_model "claude-sonnet-4-20250514"` → 현행(예: `claude-sonnet-4-6`), `OpenAIClient "gpt-4o"` → 현행. (config `model: null`일 때 이 fallback이 실제 사용됨) | backward-compat가 아니라 **출력/동작 변경**: 기본 모델을 바꾸면 같은 입력에 다른 응답 → 트레이딩 결정이 달라질 수 있음. 따라서 자동 적용 불가. | 최신 모델 품질/가격, 스테일 id가 retire되어 깨지는 위험 제거. | 기존 `claude`/`openai` provider 경로의 출력 재현성(과거 동작과 달라짐). | `strategy/llm/client.py:82,116`. 실사용: `config/settings.yaml:200`이 `model: null`이고 provider가 `claude`/`openai`일 때만. 기본 provider가 `claude_code`면 미적용. | ⬜ 승인 / ⬜ 유지(스테일 그대로) / ⬜ 보류 |

## 진행 안 함 (명시적 제외)

| # | 항목 | 이유 |
|---|------|------|
| **N-2** | 함수내 lazy import를 모듈 top으로 이동 | `_setup_intraday`의 import는 **의도적** — steering 활성 시에만 intraday 서브시스템 구성. top 이동 시 비-steering 모드에서도 강제 import + 순환참조 위험 ↑ → **개선 아님**. 유일하게 사소 이동 가능한 메서드내 `import os`(modes/agent.py:57)도 가치 미미. **드롭.** |
| 주석 | "과한 주석" 정리 | 실측 부재(최대 13%, BR/불변식 인용=고가치). baseline §A. **드롭.** |

---

## 특성화 테스트 매핑 요약 (단계 1 보강 필요 항목)

- **N-1, N-5** → `strategy/llm/`은 직접 테스트 0개. **단계 4 진입 전 `tests/test_llm_formatter.py` 신규 작성**(특성화-우선): 고정 OHLCV fixture로 `format_for_llm` 전체 출력 + `_find_resistance/support_levels` 반환값 스냅샷 고정. 이 테스트가 green인 상태에서만 N-1 리팩토링 진행, before/after 동일 유지.
- **N-4** → 기존 `test_strategies.py` rf 경로 + 1 신규(경로 밖 거부).
- **N-6** → 기존 `test_steering_commands.py` + `test_risk.py`로 충분.

## 정지 지점

- [x] T3(N-3) 항목 사용자 제시 완료
- [x] 사용자 결정: **현행 모델로 교체 승인** + audit.md 기록 완료

## Stage 4 구현 결과 (2026-05-31)

선택된 범위(N-1 + N-3 + N-7) 구현 완료. main 작업(R1 worktree 예외, 사용자 승인).

- **N-1 ✅** `data_formatter`: `_find_resistance_levels`/`_find_support_levels`를 `_find_pivot_levels(series, current, kind)` 단일 헬퍼로 통합(두 메서드는 thin wrapper 유지). **특성화-우선**: `tests/test_llm_formatter.py` 신규(현재 동작 캡처) → 리팩토링 전/후 green 동일 유지(동작 보존 확인).
- **N-3 ✅** `client.py` ClaudeClient 기본 모델 `claude-sonnet-4-20250514` → `claude-sonnet-4-6`. `gpt-4o`는 rolling alias라 유지(주석 명시). `settings.yaml` 주석 갱신. guard 테스트 추가(스테일 재발 방지).
- **N-7 ✅** F6 tsgo 수정 outward 반영: 서브모듈 `feat/f6-tsgo-box-selectable` 커밋 `813c745` → fork `main` FF → autostock-cli origin push(576b63c..813c745) → 부모 gitlink re-pin 커밋 `edfcdef`(gitlink만, Python 변경 미포함).
- **검증**: `tests/test_llm_formatter.py` 5 passed, **전체 스위트 370 passed**. tsgo(fork) 2 errors → 0.
- **미선택(미구현)**: N-4, N-5, N-6 — ledger에 후보로 보존. N-2/과한주석 드롭 유지.
- **미커밋(의도)**: Python R1 변경(client/data_formatter/settings/test)은 working tree에 둠 — 커밋 요청 시 진행.

---

## 종합 권고 (정직)

신규 표면은 건강하다. 실제로 가치 있는 작업은 **N-1(중복 제거, 단 테스트 선행)** 정도이며, N-4는 값싼 방어, N-6은 cosmetic, N-5는 저우선 additive, N-2/주석은 드롭. **N-3은 동작 변경이라 승인 없이는 손대지 않는다.**

가장 합리적인 최소 실행 묶음: **N-1 + N-4**(+ 선행 `test_llm_formatter.py`). N-5/N-6은 옵션. N-3은 사용자 결정 대기.

**N-7(F6 tsgo)**: 사용자 요청으로 즉시 진단+수정+검증 완료(타입 전용, 0 errors). submodule working tree에만 적용됨 — 커밋/포크 push/부모 re-pin은 **outward 게이트**(사용자 승인 후). F7 머지 패턴(feat 브랜치→fork main→re-pin)과 동일 절차 필요.
