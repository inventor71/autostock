# F5 — 콘솔 네이티브화 & 진입점 개선: 실행 계획 (Workflow Planning)

- **트랙**: F5 · **유형**: Brownfield 기능 추가 · **작성**: 2026-05-30
- **요구사항**: `aidlc-docs/inception/requirements/console-native-launcher.md` (승인됨)
- **리스크**: **Medium** (안전-크리티컬 주문 경로/엔진 불변; 리스크는 운영 레이어 = systemd 자동기동/포크 TUI 편집/토큰 누출 → worktree 격리로 롤백 용이)

## 1. 단계 결정 (Stage Determination)

| 단계 | 실행? | 근거 |
|------|-------|------|
| Workspace Detection | 재사용 | brownfield, 기존 프로젝트 |
| Reverse Engineering | 재사용 | 아티팩트 존재 |
| Requirements Analysis | ✅ 완료/승인 | — |
| **User Stories** | **SKIP** | 단일 오퍼레이터 도구, 워크플로는 FR-1..6으로 포착 (F2/F3/F4와 일관) |
| **Workflow Planning** | ✅ (본 문서) | — |
| **Application Design** | **SKIP** | 신규 컴포넌트 집합 작음 → Functional Design에 흡수 |
| **Units Generation** | **SKIP** | 단일 유닛 (아래 §2) |
| Functional Design (per-unit) | ✅ EXECUTE (light) | 데몬 관리 상태기계(down→start→health-wait→attach / running→attach / fail→diagnose) + 프리플라이트 판정 모델 + 리브랜딩 표면 인벤토리 |
| NFR Requirements (per-unit) | ✅ EXECUTE (minimal) | 기술스택 = 0 신규 런타임 의존(셸 + 기존 bun + 기존 TS filedrop 재사용 + systemd 유닛 파일). 빠르게 확정 |
| NFR Design (per-unit) | ✅ EXECUTE | fail-closed 프리플라이트, 토큰 마스킹, **자동기동 경합 방지**(중복 start 레이스), systemd 상호작용, 런타임 배너 |
| Infrastructure Design (per-unit) | **SKIP** | 로컬; 유일한 "인프라" = systemd user 유닛 파일 → Functional/NFR Design에 포함 |
| Code Generation (per-unit) | ✅ EXECUTE | — |
| Build and Test | ✅ EXECUTE | 프리플라이트/파서 단위테스트 + 포크 빌드/타입체크 + 파이썬 무회귀 + 라이브 검증(사용자) |

## 2. 유닛 결정 (Units)

**단일 유닛: `console-native-launcher`** (추천). 내부 빌드 시퀀스로 진행.

- **근거**: 두 결의 작업(① opencode 포크 UX 리브랜딩, ② 런처/데몬 운영)이지만 한 트랙으로 응집되고
  규모가 작아, 2-유닛 분할의 게이트 오버헤드보다 단일 유닛 내부 시퀀스가 효율적 (사용자 autonomy 선호와 일치).
- **대안(참고)**: 2 유닛 — A `console-ux`(포크 리브랜딩+사이드바 우선), B `launcher-ops`(autostock 런처+
  systemd+프리플라이트). 독립 배포 가능하나 본 트랙 규모엔 과함. → **단일 유닛 권장.**

### 내부 빌드 시퀀스 (Code Generation 단계에서 구현)
1. **S1 — 리브랜딩**(FR-2): `cli/logo.ts` 글리프 `open`+`code` → `autostock` ASCII 교체; `component/logo.tsx`
   시머 유지; 푸터/스플래시/창 타이틀/팁/about 등 보이는 "opencode" 문자열 일괄 교체.
2. **S2 — 사이드바 우선 시작**(FR-1): 홈/스플래시 우회 → 세션 뷰 직행 + autostock 사이드바 기본 표시;
   `<leader>b` 토글 보존; 입력 흐름 무파손.
3. **S3 — 프리플라이트**(FR-5, FR-6): 데몬 헬스 / 토큰 일치 / `STEERING_DIR` / MCP 경로 점검 (TS, 기존
   `filedrop`/snapshot 재사용); 실패 시 명확한 한 줄 진단+해결법, fail-closed; 토큰 마스킹.
4. **S4 — systemd 데몬 관리**(FR-4): systemd **user** 유닛(템플릿/생성+활성화); `autostock` 기동 시
   서비스 상태 확인 → 꺼졌으면 start + health-wait → attach / 이미 running이면 attach (중복기동 금지, 레이스 가드).
5. **S5 — `autostock` 런처 + 설치**(FR-3): PATH에 `autostock` 진입점(얇은 bun 런처) + 설치 스크립트;
   env(STEERING_DIR/토큰/AUTOSTOCK_ROOT) 일관 셋업 후 S3 프리플라이트→S4 데몬→콘솔 실행.
6. **S6 — 런타임 끊김 배너**(FR-5, Q6=B): 기동 후 MCP/채널 끊김 감지 → 사이드바/상단 배너 경고.
7. **S7 — 테스트 & 마감**: 프리플라이트/판정 단위테스트, 포크 타입체크/빌드, 파이썬 무회귀, **서브모듈
   편집분 커밋+재핀**, 라이브 검증(사용자 머신: `autostock` 한 줄 → 데몬 자동기동 → 사이드바 진입).

## 3. 실행 흐름 (런타임, FR-3~FR-5)

```text
  $ autostock   (PATH launcher, S5)
        |
        v
  [env setup] STEERING_DIR / token / AUTOSTOCK_ROOT
        |
        v
  [PREFLIGHT] (S3, fail-closed, token masked)
   ok? --no--> 명확한 진단 1줄 + 해결법 -> 안전 종료 (no silent exit)
   |yes
   v
  [DAEMON] (S4, systemd --user)
   running? --no--> systemctl --user start -> health-wait
        |                                        |
        |  fail --------------------------------> 진단 + 안전 종료
        v
   running/attached
        |
        v
  [CONSOLE TUI] 세션 뷰 직행 + autostock 사이드바 (S1/S2)
        |
        v
  [RUNTIME WATCH] MCP/채널 끊김 -> 사이드바/배너 경고 (S6)
```

## 4. 영향 컴포넌트
- **포크(서브모듈 `operator-console/cli`)**: `packages/opencode/src/cli/logo.ts`, `.../component/logo.tsx`,
  `.../feature-plugins/home/*`, `.../feature-plugins/sidebar/autostock.tsx`, 보이는 문자열 표면. (편집+재핀)
- **`operator-console/`**: 프리플라이트/런처 로직(기존 `src/filedrop.ts` 등 재사용) + 신규 `autostock` 진입점/설치.
- **신규 운영 파일**: systemd user 유닛(템플릿/생성), 설치 스크립트.
- **파이썬 데몬**: 코드 변경 최소(systemd로 감싸는 운영 레이어; 채널 헬스 = snapshot 읽기, Python 무변경 목표).

## 5. 확장 컴플라이언스 (Q8=A)
- Security Baseline: SECURITY-03(토큰 비노출 — S3/S6 진단), SECURITY-11(권한분리 불변), SECURITY-15(fail-closed
  기동 — S3) **적용·blocking**. 그 외 N/A.
- PBT: 대체로 N/A; 프리플라이트 판정 등 순수 함수가 생기면 선택 적용.

## 6. 진행 방식
- **worktree 격리** 후 단일 유닛 시퀀스(S1→S7) 자율 진행(설계 승인 후), 진짜 사람 판단(라이브 검증/제품 결정) 시에만 정지.
- 각 Construction 단계는 2-옵션 승인 게이트로 마감.
