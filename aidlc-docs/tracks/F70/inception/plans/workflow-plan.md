# F70 — Workflow Plan

> 요구사항 승인 후 작성. 어떤 단계를 어느 깊이로 실행할지 결정. 승인 게이트 통과 전 다음 단계 진행 금지.

## 실행 단계 결정

```text
INCEPTION
  [x] Workspace Detection ........ 완료 (brownfield, codekb 有, 신규)
  [x] Requirements Analysis ...... 완료 (Standard, 승인)
  [-] User Stories ............... SKIP
  [→] Workflow Planning .......... 현재 (ALWAYS)
  [ ] Application Design ......... EXECUTE (Standard)
  [-] Units Generation ........... SKIP (단일 유닛)

CONSTRUCTION  (단일 유닛: "benchmark")
  [ ] Functional Design .......... EXECUTE (신규 데이터 모델/스키마)
  [ ] NFR Requirements ........... EXECUTE (경량 — 격리/부하/저장)
  [ ] NFR Design ................. EXECUTE (경량)
  [ ] Infrastructure Design ...... SKIP (클라우드 인프라 없음; sandbox 계정은 기존 스크립트)
  [ ] Code Generation ............ ALWAYS
  [ ] Build & Test ............... ALWAYS
```

## 각 단계 근거

| 단계 | 결정 | 근거 |
|------|------|------|
| User Stories | **SKIP** | 외부 사용자 워크플로 없음. 단일 페르소나(개발자)가 나중에 저장된 지표를 정량 분석. 내부 측정 인프라 → 스토리가 추가 가치 없음 |
| Application Design | **EXECUTE** | 신규 컴포넌트(`src/benchmark/` 오케스트레이션)·신규 전략(buy&hold)·계정 매핑·데몬 훅 → 컴포넌트 경계/메서드/의존성 정의 필요 |
| Units Generation | **SKIP** | 작업이 하나의 응집된 단위("섀도우 러너 + equity 기록 + 지표 산출"). 다중 서비스 분해 불필요 |
| Functional Design | **EXECUTE** | 신규 데이터 모델: equity 스냅샷 스키마, benchmark config, 지표 출력 스키마. buy&hold 거래 규칙 |
| NFR Requirements/Design | **EXECUTE (경량)** | NFR-1 계정 격리(프로덕션 무영향), NFR-2 다계정 API 부하/cadence, NFR-3 저장 보존, NFR-4 재현성 |
| Infrastructure Design | **SKIP** | 신규 클라우드 리소스 없음. 페이퍼 계정은 기존 `scripts/broker_create_accounts.py` farm. 로컬 파일 저장 |

## 단일 유닛 정의

**Unit: `benchmark`** — 다음을 하나의 응집 단위로 구현:
1. **buy&hold 전략** — 레지스트리 등록(유니버스 동일가중 매수 후 보유)
2. **섀도우 러너** — baseline 5개 각각 전용 sandbox 계정 바인딩 `TradingEngine` 실행 오케스트레이션 + 토글 + 계정 매핑(fail-closed)
3. **equity 스냅샷 기록** — baseline + LLM 계정 equity 시계열을 전용 디렉토리에 JSONL append
4. **alpha-vs-baseline 지표** — 저장 시계열 → 누적수익/alpha/MDD/Sharpe 등 순수함수 산출 + 영속화

## 영향/공유 파일 (Merge Risk 예고)

- `config/` (신규 `benchmark.yaml` 또는 `strategies.yaml` 확장)
- `src/strategy/registry.py` + 신규 buy&hold 전략 파일 (등록)
- 신규 `src/benchmark/` 디렉토리 (충돌 위험 낮음)
- `src/execution/brokers/broker_api_broker.py` — **읽기/재사용만**, 변경 최소화 (R3가 Alpaca-shaped base 정리 머지됨 → rebase 시 확인)
- `main.py` / 데몬 사이클 훅 — F69(health TUI), F33 등 데몬 경로 동시 작업과 겹칠 수 있음 → 주의
- 신규 저장 디렉토리 `data/benchmark/` (gitignore 정책 확인)

## 산출물 위치

- Application Design → `aidlc-docs/tracks/F70/inception/application-design/`
- Construction 설계/코드 계획 → `aidlc-docs/tracks/F70/construction/`
- 코드 → **worktree** `.claude/worktrees/F70` (feat/F70) — Code Gen Part 2 전 worktree 생성(게이트)
