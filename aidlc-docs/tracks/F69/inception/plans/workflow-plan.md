# F69 Workflow Plan — Health Check TUI 통합

## 복잡도 평가
- 신규 컴포넌트 소수(데몬 발행 메서드+스레드, TUI 훅/글리프/오버레이) + 기존 패턴 그대로 미러.
- 데이터 스키마는 F63 `HealthReport`로 이미 확정 → 새 모델 없음.
- 단일 운영자, 위험 낮음(read-only, 비차단, 회귀 없음).
- Python(producer) + TS(consumer) 두 면을 건드리지만 하나의 응집된 기능 = **단일 유닛**.

## 단계별 실행 계획

| 단계 | 실행? | 깊이/사유 |
|------|-------|-----------|
| Workspace Detection | ✅ done | brownfield 확정 |
| Reverse Engineering | ⏭️ skip | 기존 코드 충분히 파악, 새 RE 불필요 |
| Requirements Analysis | ✅ done | standard, 승인됨 |
| User Stories | ⏭️ skip | 단일 운영자 페르소나, 순수 운영 가시화 도구 |
| Workflow Planning | ✅ (이 문서) | ALWAYS |
| Application Design | ⏭️ skip | 아키텍처 단순·기존 패턴 미러. 컴포넌트 계약은 Functional Design에 흡수 |
| Units Generation | ⏭️ skip | 단일 유닛 (Producer+Consumer 한 기능) |
| **Construction — Unit 1** | | |
| · Functional Design | ✅ minimal | 발행 스레드 수명주기·health.json 계약·TUI 훅/글리프/오버레이 컴포넌트 계약 정의 |
| · NFR Requirements | ⏭️ skip | NFR은 requirements.md(NFR-1~4)에 이미 포착(비차단/read-only/무churn/회귀없음) |
| · NFR Design | ⏭️ skip | 위와 동일 — 전용 스레드+원자적 쓰기+poll-diff로 충족, Functional Design에 반영 |
| · Infrastructure Design | ⏭️ skip | 인프라 변경 없음(기존 데몬·파일·TUI) |
| · Code Generation | ✅ ALWAYS | Python 발행 + TS 훅/글리프/오버레이 + 테스트 |
| Build & Test | ✅ ALWAYS | Python 유닛테스트(발행/graceful) + TUI 타입체크/렌더 + 라이브 스모크 |

## 영향 파일 (예상)
**Python (producer)**
- `src/agent/steering/runtime.py` — `publish_health()` 메서드 추가 (atomic_write_text)
- 발행 드라이버: 전용 스레드 (runtime 또는 agent 모드 setup). `src/trading/modes/agent.py`에서 기동.
- `config/` — health 발행 주기 설정값(기본 300s) 추가.

**TS (consumer, `operator-console/cli/packages/tui-trading`)**
- `src/hooks/use-health-data.ts` (신규) — `use-monitor-data.ts` 미러
- `src/types.ts` — HealthReport/DimensionResult TS 타입 추가
- `src/components/health-overlay.tsx` (신규) — `turn-overlay.tsx` 패턴
- 상단바 글리프: 기존 status/Nav 컴포넌트에 글리프 셀 + 클릭 핸들러 (호스트 앱 wiring 포함)
- `src/index.ts` — export 추가

## worktree
- Code Generation Part 2 **전에** `git worktree add .claude/worktrees/F69 -b feat/F69` (base ec2875c).
- 설계 문서(현 단계)는 worktree 전이라도 main 트리의 `aidlc-docs/`에서 작성 가능.

## 산출물
- 동작하는 Python 발행 + TUI 표시, 테스트, build-and-test 지침, post-merge-guide
  (운영자 가시 변경이므로 CONDITIONAL 가이드 작성 대상).
