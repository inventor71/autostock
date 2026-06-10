# Track R12 — `execution/brokers/` 네이밍 정합

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: R12
- **Title**: `broker_api_broker` 개명 + `simulated`→`simulated_broker` 접미사 통일 + `kis_*`→`brokers/kis/`
- **Type**: refactor
- **Status**: merge-awaiting  <!-- Build & Test green (1073) + critic 반영 + T3-1/T3-2 승인 구현; code on refactor/R12 -->
- **Branch**: refactor/R12
- **Worktree**: .claude/worktrees/R12
- **Submodule branch**: — (Python only)
- **Base commit**: 0106a8b (main HEAD; R9/R11 merge-awaiting — main.py/runner.py 라인 분리)
- **Start Date**: 2026-06-11

## Extension Configuration
- **Security Baseline**: Applicable — 브로커 자격증명은 이미 env-sourced; **개명만** 하고 키/엔드포인트
  처리 면을 바꾸지 말 것. 새 인증/네트워크 면 없음(N/A).
- **Property-Based Testing**: Enabled 가능 — `tests/test_broker_api_broker.py`의 mapper PBT가 개명 후에도
  green인지로 동작 보존 확인.

## Scope
`execution/brokers/` 네이밍이 헷갈린다(점검 #6, MEDIUM):
- `broker_api_broker.py` — 이름만으론 무슨 브로커인지 불명확(레지스트리상 sandbox account-farm 어댑터).
- `simulated.py` 만 `_broker` 접미사 없음(`alpaca_broker.py`/`kis_broker.py`와 불일치).
- `kis_{broker,pricing,rest}.py` 3개 → `brokers/kis/` 서브패키지 후보.

**개명 — 순수 T1, 동작 보존**:
- `broker_api_broker.py` → 의미 있는 이름(예: `sandbox_broker.py` 또는 `account_farm_broker.py`) —
  Stage 3에서 도메인 의미로 확정. 클래스 `BrokerApiBroker` 도 동반 개명.
- `simulated.py` → `simulated_broker.py` (접미사 통일).
- `kis_{broker,pricing,rest}.py` → `brokers/kis/{broker,pricing,rest}.py`.
- 유지: R3에서 추출한 `_alpaca_shaped.py` 베이스, `alpaca_broker.py`, `session_timeout.py`.

**함수/심볼 네이밍 전수검사 (요구사항)**: 실제 브로커 디스패치 site는 **`main.py:36 create_broker()`**
(`settings.broker.provider == "broker_api"` → `BrokerApiBroker`, `settings.broker.name == "kis"` →
`KisPaperBroker`)이고, 선택 문자열 키는 **`config/config.py:24 BrokerConfig.{provider,name}`** (기본
`provider="alpaca"`), 읽는 곳은 `src/monitoring/health/dimensions/config_env.py:73`. (`universe/factory.py`·
`trading/modes/*`에는 브로커 선택이 **없다** — 거기 보지 말 것.) 이 site들 + 클래스 import를 `rg`로
전수 조사 후 일괄 변경. 테스트 green 유지, shim 없이 직접 갱신.

**중요 — 외부 config 리터럴 분리**: 모듈/클래스(`broker_api_broker`/`BrokerApiBroker`)는 코드 식별자라
개명이 T1이지만, `provider: "broker_api"` 는 배포된 `config/settings.yaml`에 박힌 **외부 문자열 키**라
바꾸면 호환성 깨짐(T2/T3 + 마이그레이션). 둘은 decoupled. **결정(2026-06-08): 클린 브레이크** — `provider:"broker_api"` 리터럴도 의미 있는
이름으로 함께 개명, **하위호환 별칭 없이** 동일 PR에서 `config/config.py`의 기본값 + 모든 in-repo
config(`config/*.yaml`) + 운영 `settings.yaml`/cron/runbook 를 직접 갱신. 단일 운영자라 가능 —
**post-merge-guide 필수**(머지 시 settings.yaml의 `provider` 값을 새 이름으로 바꿔야 데몬 부팅).
→ T-등급: **코드 개명 T1 + 의도된 외부 표면 변경**(silent-T1 아님).
**KIS 결합 주의**: `kis_broker.py`는 클래스 2개(`KisBroker`+`KisPaperBroker`)를 담고, REST 클라이언트를
`src/data/providers/kis_provider.py`와 공유(`main.py:15-18`) → `kis_*`→`brokers/kis/` 이동 시 data-provider
import까지 동반 수정.

## Merge Risk Notes
- **공유 파일 (주의)**: `src/execution/brokers/**` + **`main.py`(create_broker)** + `config/config.py`(BrokerConfig)
  + `src/monitoring/health/dimensions/config_env.py` + `src/data/providers/kis_provider.py`(KIS REST 공유)
  + `tests/test_{alpaca,broker_api,kis}_*`.
- **API/시그니처 변경**: 모듈/클래스명 다수 개명. 브로커 선택 문자열 키가 외부면 주의.
- **알려진 동시 변경 / 권장 순서**: R3(merged) 후속. 다른 R-트랙과 거의 안 겹침 → R11 다음(R12) 권장.

## Stage Progress (skill: ai-dlc-refactor)
- [x] Stage 1 — Baseline (`1-baseline.md`; 모듈3그룹 참조 전수 + provider 리터럴 인벤토리(운영 yaml=alpaca 확인); broker 테스트 133 green)
- [x] Stage 2 — Tier ledger (`2-tier-ledger.md`) — T1 6항목 + T3 1(클린브레이크, 사전승인+이름확정)
- [x] post-merge-guide — `post-merge-guide.md` (provider 마이그레이션 + 재시작/스모크/롤백)
- [x] Stage 3 — Redesign (`3-redesign.md`) — **새 이름 = account_farm**(UAQ 2026-06-11) + kis/ 서브패키지 + 마이그레이션 순서
- [x] Stage 4 — Implementation — git mv 5+테스트1; 클래스/모듈/리터럴 전수 갱신(33파일); T3-2 raise; 잔여 0
- [x] Build & Test — 전체 **1073 passed**; broker 137; create_broker 4분기 스모크(구 리터럴 fails-loud 확인)
- Status: **merge-awaiting**
