# F83 — Execution Plan (Workflow Planning)

> 승인 2026-06-14 기준. 요청 복잡도: 중(신규 공유 인프라 + 동작보존 마이그레이션 +
> 언어 경계 정합). Risk: Medium (공유 패키지 신설·TUI 회귀·monorepo 빌드 배선).

## 실행 단계 (EXECUTE / SKIP)

### INCEPTION
- [x] Workspace Detection
- [x] Reverse Engineering — **SKIP** (CodeKB + 직접 조사 충분)
- [x] Requirements Analysis — **EXECUTE** (standard, 승인됨)
- [x] User Stories — **SKIP** (내부 인프라, 운영자=개발자 1명)
- [~] Workflow Planning — **EXECUTE** (본 문서)
- [ ] Application Design — **EXECUTE**: 공유 패키지 경계·카탈로그 자료구조·게이트 API·
  TUI 마이그레이션 매핑·Python 대조테스트 메커니즘·monorepo 빌드 배선 설계. 보안 경계 통합.
- [ ] Units Generation — **SKIP** (단일 패키지 유닛 `artifacts` + TUI 소비측 편집)

### CONSTRUCTION (단일 유닛: artifacts 패키지 + TUI 마이그레이션)
- [ ] Functional Design — **EXECUTE**: 카탈로그 엔트리 스키마(zod), 게이트 API 시그니처,
  안전읽기 3종 알고리즘(viz-shell 이식), drift 대조 규약, TUI 훅별 교체 매핑.
- [ ] NFR Requirements — **SKIP** (requirements NFR-1~7로 확정)
- [ ] NFR Design — **SKIP** (Application Design에 통합)
- [ ] Infrastructure Design — **SKIP** (배포 인프라 없음 — 로컬/CI 빌드만)
- [ ] Code Generation — **EXECUTE** (Part 1 계획 / Part 2 생성; worktree 게이트 feat/F83)
- [ ] Build & Test — **EXECUTE** (패키지 단위/PBT + TUI 빌드·회귀 스모크 + drift 대조 CI)

## 핵심 설계 쟁점 (Application Design에서 확정)

1. **패키지 위치/이름**: `operator-console/cli/packages/artifacts`(bun workspace).
   이름 컨벤션(`@tui-trading/artifacts` vs `@autostock/artifacts`) — 기존 `@tui-trading/core`
   참조. zod는 workspace catalog 4.1.8 핀 사용(viz-shell의 4.4와 별개 — viz-shell 무접촉).
2. **카탈로그 자료구조**: 엔트리 = `{id, path, read, schema, fixture}`. 읽기전략 enum.
   루트 주입 방식(`steeringDir`/`workspaceDir` 분리 유지 vs 단일 `AUTOSTOCK_ROOT`) 결정.
3. **게이트 API**: `readArtifact`/`tailArtifact`/`readMarkdownArtifact` 형태 + 반환 타입(zod infer).
4. **안전읽기 이식**: viz-shell `safe-read.ts` 3종을 패키지로 재작성(코드 복제 — vibeshell에서
   직접 못 가져옴, 동등 구현). code-review 반영판(bytesRead·stat-stable) 기준.
5. **TUI 마이그레이션 매핑**: 5훅(snapshot/health/monitor/session/thesis) → 게이트 호출.
   자체 타입(PositionInfo 등) → 카탈로그 스키마. 폴링 간격·표시 동작 보존.
6. **drift 대조 메커니즘**: 픽스처(샘플) + 가능 시 리포 실파일을 zod로 parse하는 테스트.
   신규 엔트리 픽스처 필수 규약.
7. **승격 경로(B안) 호환**: 엔트리 정의를 나중에 Python에서 생성 가능하도록 선언형 유지.

## 동시 트랙 충돌 주의
- F79(모바일 PWA), F80/F82(intraday store/parquet) — 산출물 *생산* 표면 변경 가능.
  카탈로그는 소비측이라 직접 충돌 적으나, 산출물 스키마 변동 시 대조테스트가 잡아줌.
- TUI(`@tui-trading/core`) 동시 편집 트랙 없는지 머지 시 확인.

## Risk 평가
- **Medium**: 공유 패키지 신설(빌드 배선) + TUI 동작보존 마이그레이션이 주 리스크.
  완화 = 동작보존 회귀 스모크 + drift 대조 CI + viz-shell 검증된 원형 재사용.
