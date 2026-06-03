# F5 — 콘솔 네이티브화 & 진입점 개선: 요구사항 (Requirements)

- **트랙**: F5 (F4 opencode 하드포크 operator console 위에 얹는 후속 작업)
- **유형**: Brownfield 기능 추가/개선
- **작성**: 2026-05-30 · **깊이**: Standard
- **상태**: Requirements Analysis 승인 대기 (질문 8개 답변 완료, 모순 없음)

## 1. 목적 / 가치
F4에서 만든 operator console를 **더 편하고 stock에 native하게** 만든다. 헤드라인 가치:
- 켜자마자 **트레이딩 상황판(사이드바)** 이 보여 바로 운용 가능 (opencode 코딩 홈 화면을 거치지 않음).
- **autostock** 브랜드로 일관 (opencode 흔적 제거 — 트레이딩 전용 도구로 인지).
- `claude`처럼 **`autostock` 한 줄**로 어디서든 실행. 데몬은 알아서 떠 있고, 잘못되면 **조용히 죽지 않고
  명확히 알려준다** (silent failure 제거 = 운용 신뢰성).

## 2. 확정된 결정 (질문 답변, 2026-05-30)
| Q | 결정 | 요지 |
|---|------|------|
| Q1 | **A** | 홈/스플래시 건너뛰고 **바로 세션 뷰 + autostock 사이드바 기본 표시** |
| Q2 | **B** | ASCII 로고 + **보이는 "opencode" 문자열 전부** autostock으로 일괄 리브랜딩 |
| Q3 | **A** | systemd 관리 대상 = **파이썬 트레이딩 데몬**(`main.py --mode agent --steering`); 콘솔은 포그라운드 TUI로 **attach**, 데몬 꺼져있으면 콘솔 기동 시 자동 기동 |
| Q4 | **A** | **systemd user 서비스**(`systemctl --user`) 사용. (사용자 단서: systemd 활성화에 문제 생기면 그때 재결정) |
| Q5 | **A** | **`autostock` 단일 명령을 PATH에 설치**하는 얇은 런처(bun 런타임). 진짜 컴파일 바이너리 아님 |
| Q6 | **B** | **기동 프리플라이트** + **런타임 끊김 경고**(사이드바/배너)까지 |
| Q7 | **A** | 진단/로그에 **토큰 값 절대 비노출**(존재·일치 여부만), 실패 메시지도 마스킹 |
| Q8 | **A** | 확장 = 프로젝트 기본값 (Security Baseline Enabled; PBT는 대체로 N/A) |

### 환경 검증 (2026-05-30)
Q4=A의 전제(systemd)가 이 WSL2 환경에서 **실제로 충족됨**: PID 1 = `systemd`,
`systemctl --user is-system-running` = `running`, `/etc/wsl.conf`에 `systemd=true`,
user-systemd 런타임 present. → **Q4 재결정 단서는 발동 안 함.** bun 1.3.14 = `~/.bun/bin/bun`.

## 3. 기능 요구사항 (FR)

### FR-1 — 사이드바 우선 시작 (Q1=A)
- 콘솔 기동 시 opencode 홈/스플래시(`feature-plugins/home/`: 로고 + "Ask anything..." + 팁)를
  거치지 않고 **세션 뷰로 직행**하며 **autostock 사이드바(`feature-plugins/sidebar/autostock.tsx`)가
  기본 표시** 상태여야 한다.
- 사이드바 토글(`<leader>b`)은 유지(끄고 켤 수 있음) — 기본값만 ON/표시로 바뀜.
- 세션 직행이 opencode 정상 입력 흐름을 깨지 않아야 한다(프롬프트 입력/명령 사용 가능).

### FR-2 — autostock 리브랜딩 (Q2=B)
- 홈 ASCII 로고(`cli/logo.ts`의 `logo`/`go` 글리프, `component/logo.tsx` 시머 렌더)를
  **"autostock"** 글리프로 교체. 시머 애니메이션 효과는 유지.
- **눈에 보이는 "opencode" 문자열을 전부 autostock으로** 교체: 푸터/스플래시/창(터미널) 타이틀/about/팁 등
  사용자에게 노출되는 표면. (내부 패키지명/import 경로 등 비노출 식별자는 교체 대상 아님 — §7 비범위.)

### FR-3 — `autostock` 진입 명령 / 설치 (Q5=A)
- `cd operator-console/cli && bun dev` 대신 **PATH에 설치된 `autostock` 명령** 하나로 콘솔을 띄운다.
- 형태 = **얇은 런처**(bun 런타임 사용; 진짜 단일 컴파일 바이너리 아님). 설치 = 설치 스크립트
  (PATH에 `autostock` 진입점 배치). `claude`처럼 어느 디렉터리에서든 `autostock` 실행 가능.
- 런처는 환경(STEERING_DIR / 토큰 / `AUTOSTOCK_ROOT` 등)을 일관되게 셋업하고 콘솔을 실행한다.

### FR-4 — 데몬 자동 기동 / attach (Q3=A, Q4=A)
- 트레이딩 데몬(`python main.py --mode agent --steering`)을 **systemd user 서비스**로 관리.
- `autostock` 실행 시:
  - 데몬 서비스가 **꺼져 있으면 자동 기동**(`systemctl --user start …`) 후 헬스 확인하고 콘솔 attach.
  - **이미 돌고 있으면** 그대로 **attach**(중복 기동 금지).
- 콘솔은 데몬과 **repo-root `steering/` 파일드롭 채널로만** 통신(기존 계약 불변). "attach" = 같은
  `STEERING_DIR`/토큰으로 채널에 붙는 것.
- 서비스 유닛 설치/활성화(최초 1회)도 런처/설치 흐름에서 처리(수동 systemctl 편집 불필요).

### FR-5 — 프리플라이트 & silent-failure 제거 (Q6=B, Q3 단서)
- 콘솔 기동 전 **프리플라이트 점검**을 수행하고, 실패하면 **명확한 한 줄 진단 + 해결 방법**을 출력하고
  **안전하게 중단**(fail-closed). **절대 tool을 못 켠 채 조용히 종료하지 않는다.**
- 최소 점검 항목:
  1. **데몬 헬스** — 서비스 상태 / 채널(snapshot) 응답 여부 (꺼져있으면 FR-4로 기동, 기동 실패면 진단).
  2. **토큰 일치** — 콘솔 env 토큰 == 데몬 root `.env` 토큰 (불일치 시 "채널이 모든 명령을 bad-token으로
     거부 → 명령 안 먹힘" 증상을 사전 차단).
  3. **`STEERING_DIR` 존재/접근** 가능.
  4. **MCP 서버 경로 해석 가능** — `autostock_steer` MCP가 로드되도록 절대경로/`{env:}` 정상.
     (메모리 기록된 실패: 상대경로 → "Module not found" → MCP 미기동 → 모델이 "주문 못 한다"고만 말함.)
- **런타임 감지(Q6=B)**: 기동 후에도 MCP/채널 끊김을 감지하면 **사이드바/상단 배너에 경고**를 표시한다
  (조용한 반-기동 상태 방지).

### FR-6 — 비밀 취급 (Q7=A)
- 프리플라이트/진단/로그/배너 어디서도 **operator 토큰 값을 출력하지 않는다**. 존재·일치 여부(boolean)만
  표시. 실패 메시지에서도 마스킹. (SECURITY-03)

## 4. 비기능 요구사항 (NFR)
- **NFR-1 (안전 아키텍처 불변)**: 콘솔의 주문 권한 없음(제안→사람 confirm→데몬 RiskManager→Broker 게이트),
  agent 세션의 권한분리(토큰 구조적 비접근)는 **그대로 유지**. 이 트랙은 UX/진입점/운영성만 바꾼다.
- **NFR-2 (fail-closed 기동)**: 프리플라이트 실패 = 안전 중단 + 안내. 부분 기동/silent exit 금지. (SECURITY-15)
- **NFR-3 (비밀 비노출)**: FR-6. (SECURITY-03)
- **NFR-4 (계약 불변)**: `steering/` 파일드롭 계약(commands/events/snapshot/토큰)과 Unit A 데몬 엔진은
  변경하지 않는다. F5는 그 위의 런처/콘솔 UX 레이어.
- **NFR-5 (현행 무회귀)**: 기존 콘솔 기능(NL→MCP steer, 사이드바, 락다운)과 파이썬 테스트 스위트는
  회귀 없이 유지.
- **NFR-6 (이식성 경계)**: systemd user 서비스 전제(Q4=A). 비-systemd 환경은 명확한 에러로 안내(재결정 단서).

## 5. 확장 (Extensions) — Q8=A
- **Security Baseline = Enabled**. 적용:
  - SECURITY-03 (비밀 비노출) — FR-6/NFR-3, 새 진단 출력이 토큰을 흘리지 않도록 **핵심**.
  - SECURITY-11 (권한분리) — NFR-1, 콘솔/agent 권한 경계 불변.
  - SECURITY-15 (명시적 에러/ fail-closed) — FR-5/NFR-2, 이 트랙의 헤드라인.
  - 그 외(웹/DB/IaC/사용자 인증 등)는 N/A.
- **Property-Based Testing = 대체로 N/A** (런처/TS UX). 결정성 순수 함수(예: 프리플라이트 판정 로직)가 생기면
  선택적 example/Hypothesis 적용 가능.

## 6. 범위 / 영향 표면
- **opencode 포크(서브모듈 `operator-console/cli`)**: 홈 화면 우회 + 사이드바 기본 표시(FR-1), 로고/문자열
  리브랜딩(FR-2), 런타임 끊김 배너(FR-5). → 포크 편집 + 서브모듈 재핀 필요.
- **`operator-console/` (TS, 포크 밖)**: 런처/프리플라이트 로직이 들어갈 후보 위치(또는 신규 스크립트).
- **신규**: `autostock` 진입점 + 설치 스크립트 + systemd user 유닛(템플릿/생성).
- **파이썬 데몬**: 코드 변경 최소(서비스로 감싸는 운영 레이어). 헬스/채널 계약 재사용.

## 7. 비범위 (Out of scope)
- 명령 경로 재설계(NL-only 결정 불변 — 키스트로크 경로 재도입 안 함).
- 진짜 컴파일 단일 바이너리(`bun --compile`) — Q5=A로 얇은 런처 선택.
- 비-systemd portable supervisor(Q4=A; 환경 문제 시 재결정).
- 내부 비노출 식별자(패키지명/import 경로)의 opencode→autostock 개명.
- 사이드바 마우스 드래그 리사이즈(별도 F-future 트랙).

## 8. 다음 단계 후보 (이후 게이트에서 확정)
- User Stories: **SKIP 후보** (단일 오퍼레이터 도구, 워크플로는 FR로 포착 — F2/F3/F4와 일관).
- Workflow Planning: 실행. 단일 트랙이지만 **opencode 포크 UX** vs **런처/데몬 운영** 두 결의 작업 →
  단일 유닛 내부 시퀀스 or 2-유닛 분할은 Planning에서 결정.
- Construction: Functional/NFR/Code Generation 실행, Infra Design SKIP(로컬). worktree 분리.

## 9. 리스크
- **Medium.** 안전-크리티컬 주문 경로/엔진은 불변(NFR-1/4)이라 핵심 리스크 낮음. 리스크는 운영 레이어:
  systemd 유닛/자동기동 경합, 포크 홈/로고 편집의 TUI 깨짐, 토큰 누출. worktree 격리로 롤백 용이.
- opencode 포크 = 서브모듈이라 편집분 **커밋+재핀** 누락 주의(기존 노트 참고).
