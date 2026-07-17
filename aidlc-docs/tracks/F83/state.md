# Track F83 — 공유 산출물 카탈로그 (SSOT): 경로·읽기전략·스키마 단일 소스 + 공통 read 게이트

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F83
- **Title**: 공유 산출물 카탈로그 (SSOT) — 데몬 산출물 {경로+읽기전략+스키마} 단일 소스 + TUI/viz-shell/mobile 공통 read 게이트
- **Type**: feature (신규 공유 인프라 + 기존 소비자 점진 마이그레이션)
- **Status**: abandoned (2026-06-14, critic 검증 후 사용자 결정 — 아래 사유). **재개 트리거
  재정의 2026-06-22**: 전제(viz-shell 지표)는 충족됨(F73이 Tier 0→3 완료) — 그러나 사용자 결정으로
  **vibeshell(F73)이 main에 머지된 뒤** 성숙한 카탈로그 원형(paths/safe-read/schemas + 16 tRPC
  query)을 공유 패키지로 **추출**하는 시점에 재개. 그때까지 abandoned 유지(코드 미작성).

> **철회 사유 (critic 라운드 + 사용자 결정, 2026-06-14)**: 트랙 명분 3기둥이 코드 검증에서
> 약화됨 — ① "TUI torn-read 무방비"=거짓(producer `atomic_write_text`/`os.replace`로 snapshot·
> monitor·health 원자적, decisions/turns는 reader가 이미 torn-safe, positions/*.md만 비원자인데
> 그건 F76 담당), ② "3소비자 통합"=실질 TUI 1(mobile은 Python steer_read 경유, viz-shell은
> NFR-1로 제외), ③ 확장성은 *읽기*만 표준화하고 원래 문제(viz-shell 지표 부족)는 우회.
> 순서가 뒤집힘 → 사용자가 "viz-shell 지표 먼저"(순서 정상화) 선택. **설계 문서(requirements/
> application-design/critic 분석)는 보존** — viz-shell 지표가 안정돼 카탈로그가 viz-shell 내부에
> 자란 뒤 공유 패키지로 추출할 때 재개 참조. 미해결 설계과제(sync/async, tail vs 전체읽기,
> zod 4.1.8↔4.4 핀)도 그 문서에 기록됨.
- **Branch**: feat/F83 (TBD — Code Gen Part 2 전 생성)
- **Worktree**: .claude/worktrees/F83 (TBD)
- **Submodule branch**: — (monorepo)
- **Base commit**: d8ceda3 (트랙 생성 시점 main)
- **Start Date**: 2026-06-14T00:00:00Z

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | Yes (전체 blocking; 스테이지별 N/A 판정 허용) | Requirements (2026-06-14, viz-shell 선례 동일 적용 — 산출물 경로 화이트리스트·경로주입 차단·읽기전용) |
| Property-Based Testing | Partial (순수 함수 한정 — 안전읽기 3종/zod 변환 라운드트립, fast-check) | Requirements (2026-06-14) |

## Scope
데몬(Python producer)이 `steering/`·`workspace/`에 쓰는 json/jsonl/md 산출물의
**{경로 + 읽기전략(atomic/tail/stat-stable) + 스키마}를 단일 소스(SSOT)로** 정의하고,
세 소비자가 같은 게이트를 타게 한다:
- **TUI** (`operator-console/cli/packages/tui-trading/`): 현재 `readFileSync` 직격 +
  자체 타입 (snapshot/health/monitor/thesis/session). torn-read 무방비.
- **viz-shell** (vibeshell 브랜치 — **미머지**): 자체 `paths.ts`+`safe-read.ts`+`schemas.ts`
  (zod). 카탈로그의 사실상 원형.
- **mobile** (F71 PWA, opencode serve): operator-console 위에 얹힘 — 데이터 경로 확인 필요.

### 핵심 제약 (사용자 명시)
> **viz-shell은 아직 머지되지 않은 장기 브랜치(vibeshell).** 카탈로그를 main에 두되
> viz-shell이 main 카탈로그에 **빌드 의존성을 갖지 않게** 설계 — vibeshell이 나중에
> main을 rebase해 가져온 뒤 자체 paths/safe-read/schemas를 카탈로그로 교체. 즉 이 트랙은
> **main 측(카탈로그 신설 + TUI/mobile 마이그레이션)** 까지만 하고, viz-shell 교체는
> vibeshell 브랜치의 후속 작업으로 분리.

### 결정 (Requirements UAQ, 2026-06-14)
- **카탈로그 형태 = A안**: TS 공유 패키지 `@autostock/artifacts`(경로 카탈로그 + zod 스키마
  + 안전읽기 게이트). Python producer 무변경, CI 대조 테스트로 정합. 근거: 소비자 2/3이
  TS, viz-shell zod+safe-read 원형 활용, 엔트리=4튜플(경로+읽기전략+zod+픽스처)로 묶어
  신규 지표 추가가 단일 등록 지점. **codegen(B)으로 승격 가능하게 설계**(장기 경로).
- **범위 = 카탈로그 + TUI 마이그레이션**: 공유 패키지 신설 + tui-trading 읽기 훅
  마이그레이션. viz-shell·mobile은 후속.
- **drift 방지 = Python 대조 테스트**: zod 스키마 ↔ 실 산출물 샘플 CI 대조.

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성.

- **공유 파일 (주의)**: `operator-console/cli/packages/tui-trading/src/hooks/*` (TUI 읽기 훅 —
  마이그레이션 대상). 동시 트랙 다수(F79 모바일 PWA, F80/F82 parquet/intraday store)가
  산출물 표면을 건드릴 수 있음 — 산출물 *생산* 경로 변경과 충돌 주의.
- **API/시그니처 변경**: 신규 공유 모듈 추가가 주. 기존 producer 경로는 무변경 원칙.
- **알려진 동시 변경**: F79(mobile 뷰), F80/F82(intraday store) — 카탈로그가 이들 산출물도
  포함할지 Requirements에서 결정.

## Stage Progress
### 🔵 INCEPTION PHASE
- [x] Workspace Detection — brownfield (조사 완료: TUI readFileSync 직격 6훅 / viz-shell zod / mobile=opencode)
- [x] Reverse Engineering — SKIP (CodeKB baseline + 직접 조사 충분)
- [x] Requirements Analysis — standard, 승인 2026-06-14 (`inception/requirements/requirements.md`)
- [x] User Stories — SKIP (내부 인프라 트랙, 운영자=개발자 1명)
- [x] Workflow Planning — 승인 2026-06-14 (`inception/plans/execution-plan.md`)
- [~] Application Design — 4문서 작성 (`inception/application-design/`), **승인 대기**
- [ ] Units Generation — SKIP (단일 패키지 유닛)

### 🟢 CONSTRUCTION PHASE
- [ ] (Requirements/Design 후 확정)

## Current Status
- **Lifecycle Phase**: INCEPTION
- **Current Stage**: Application Design (승인 대기)
- **Next Stage**: Functional Design (CONSTRUCTION 진입)
