# F73 — viz-shell 요구사항 (읽기 전용 생성형 대시보드 사이드카)

## 1. 의도 분석 (Intent Analysis)

- **사용자 요청**: vibeOS 패턴 "방향 A"의 autostock 이식 — 읽기 전용 생성형 대시보드
  사이드카 `viz-shell/` 구축. 별도 브랜치 `vibeshell`에서 장기 진행, 충분히 안정된 후에만
  main 머지.
- **요청 유형**: New Feature (신규 사이드카 앱 추가)
- **범위 추정**: Multiple Components — 단, 전부 **신규** 디렉토리(`viz-shell/`) 안.
  기존 Python 데몬/operator-console **무변경** (산출물 파일 읽기 전용 소비).
- **복잡도 추정**: Moderate — 스택 자체(Next.js+tRPC)는 평이하나, Claude Code SDK
  통합·편집 경계 강제·읽기 전용 보장이 설계 포인트.
- **요구사항 깊이**: Standard

### 참조 분석 (vibeOS 백엔드 조사, 2026-06-11)
[caffeinum/vibeOS](https://github.com/caffeinum/vibeOS) 코드 분석 결론 — 차용할 4조각 패턴:
1. **repo 쓰기 권한을 가진 에이전트 = UI 생성기** (Claude Code SDK `query()` 인프로세스 호출)
2. **핫리로드 dev 런타임 = 반응성 계층** (Next.js Fast Refresh가 곧 렌더링 엔진)
3. **고정 타입세이프 서비스 계층(tRPC) = 일회용 생성 UI ↔ 실제 능력 사이의 경계**
4. **상시 채팅 패널 = 셸**

vibeOS에서 **차용하지 않는 것**: `permissionMode: "bypassPermissions"`, 무인증 terminal
라우터(임의 셸 실행), 글로벌 단일 세션 가정, mock 데이터.

## 2. 기능 요구사항 (FR)

### FR-1: 사이드카 앱 골격
- 레포 루트에 `viz-shell/` 신규 디렉토리 — Next.js(App Router) + TypeScript + Tailwind +
  tRPC, 런타임/패키지매니저 bun (operator-console과 동일 계열).
- `bun run dev`(Next.js dev 서버, HMR 활성)로 구동하는 **로컬 사이드카**.
  데몬/launcher 통합 없음 — 수동 실행.
- 기존 Python 데몬, `operator-console/`, `steering/` 계약 **코드 무변경**.

### FR-2: 읽기 전용 데이터 라우터 (MVP = 포트폴리오 코어)
- tRPC 라우터로 다음 파일 표면을 **읽기 전용** 노출. 표면별 쓰기 방식이 달라
  **읽기 전략도 표면별로 다르다** (critic 라운드에서 생산자 코드 검증, 2026-06-12):
  - `steering/snapshot.json` — 계좌/포지션/데몬 상태 스냅샷.
    생산자가 **원자적 쓰기**(`steering/channel.py` → `atomic_write_text`) — 단순 read 안전.
  - `workspace/equity.jsonl` — 에쿼티 커브 (+벤치마크 필드).
    생산자가 **append-only**(`src/agent/logs/equity.py`) — torn-line safe tail로 읽기
    (마지막 불완전 라인 무시 — `operator-console/src/filedrop.ts`의 events tail 패턴.
    단, 그 패턴은 filedrop의 events 전용이며 snapshot/thesis 읽기에는 없음 — 일반화해 구현).
  - `workspace/positions/` — 포지션별 thesis 파일. **jsonl 레코드가 아니라 통짜 마크다운
    문서**이고, 생산자 `Journal.write_position`(`src/agent/journal.py:224`)이 **비원자
    `write_text`** — 데몬 턴 중 읽으면 잘린 파일을 받을 수 있다. 리더 측 torn-read
    대응 필수: 짧은/비정상 읽기 감지 시 재시도(retry-on-short). 콘텐츠는 opaque
    markdown으로 취급(zod 스키마 파싱 대상 아님).
    (생산자를 `atomic_write_text`로 바꾸는 1줄 수정은 "데몬 무변경" 원칙에 따라 본 트랙
    범위 외 — 후속 트랙 옵션으로 기록.)
- 파일 직접 읽기(데몬 IPC 없음).
- 라우터 구조는 후속 표면(결정/턴, 체결, 시그널/헬스) 추가가 라우터 파일 1개 추가로
  끝나도록 확장 가능하게 설계. **MVP에서는 포트폴리오 코어만 구현.**
  후속 표면 중 스크리닝은 F72가 이미 출하한 계약(`workspace/screening/` +
  `filedrop.ts`의 `readScreening`)을 재사용한다 — 재발명 금지.

### FR-3: 채팅 패널 → 뷰 생성 엔진 (Claude Code SDK)
- 대시보드에 상시 채팅 패널. 메시지는 `/api/chat` → `@anthropic-ai/claude-code` SDK
  `query()` 인프로세스 호출로 전달, 응답 텍스트는 스트리밍 표시.
- **인증: 호스트의 기존 claude CLI 구독 자격(`~/.claude`) 재사용.** 별도
  ANTHROPIC_API_KEY 불요(데몬 agent 턴과 동일 방식).
- SDK의 편집 권한은 **`viz-shell/src/generated/` 이하로만 제한**. 경계 메커니즘은
  **능동 거부 콜백이 필수**다 (critic 라운드 반영, 2026-06-12):
  - SDK에는 "경로 단위 편집 allowlist" 1급 옵션이 없다. `cwd` 설정은 쓰기 경로를
    제한하지 않으며(Write/Edit는 절대경로·`../` 탈출 가능), 수동적 permission 설정만으로는
    불충분. **`canUseTool` 콜백(또는 PreToolUse 훅)에서 모든 Edit/Write 대상 경로를
    `path.resolve()`로 정규화해 `viz-shell/src/generated/` 밖이면 hard-deny** —
    이것이 유일하게 검증 가능한 경계이며 협상 불가 요건이다.
  - `bypassPermissions` 금지. 셸 실행류 도구(Bash 등)는 도구 수준에서 차단.
  - **prompt injection 경로 포함**: 에이전트가 읽는 데이터(예: thesis .md)에 악성 지시가
    들어 있어도 경계가 유지되어야 한다 — 경계는 프롬프트가 아니라 콜백 코드로 강제.
  - 참고: vibeOS의 실제 안전 경계는 Docker 컨테이너였다(`bypassPermissions`를 컨테이너
    격리로 상쇄). 본 설계는 호스트에서 구독 자격으로 실행하므로 콜백 경계가 그 대체물이다.
    추가 격리(컨테이너 실행)는 안정화 단계의 강화 옵션으로 남긴다.
- 생성된 컴포넌트는 `generated/` 디렉토리 **자동 레지스트리**(webpack `require.context`류
  글롭 임포트)로 대시보드에 마운트 — **에이전트는 컴포넌트 파일 1개만 쓰면 되고**,
  index/registry 파일을 함께 수정해야 하는 2-파일 프로토콜은 금지(누락 시 조용한 실패).
  Next.js HMR(dev 모드)로 화면 반영. 생성 뷰는 **lazy-load + error boundary**로 마운트해
  깨진 생성물이 셸 전체를 죽이지 못하게 한다.

### FR-4: 생성 뷰의 데이터 접근 경로 단일화
- 생성된 컴포넌트가 데이터에 닿는 경로는 **FR-2 tRPC 라우터 하나뿐**이다
  (생성 코드가 fs를 직접 읽거나 외부 API를 직접 치지 않도록 시스템 프롬프트 + 코드 리뷰
  경계로 강제). 라이브 갱신은 tRPC 쿼리 폴링(react-query refetch)으로 충분.

### FR-5: 기본 대시보드
- 첫 화면: 채팅 패널 + 생성 뷰 마운트 영역 + (시드용) 최소 기본 뷰 1개
  (예: 스냅샷 기반 포지션/에쿼티 요약 카드 — 생성 뷰가 참조할 모범 예제 역할).

### FR-6: 생성물 영속성 (1차)
- 생성된 뷰는 `generated/` 아래 **파일로 남고 git 추적 대상**이다(세션 휘발 아님).
- "검증된 뷰의 정식 승격"(방향 B 자동화)은 **본 트랙 범위 외** — 후속 트랙.

## 3. 비기능 요구사항 (NFR)

### NFR-1: 읽기 전용 보장 (최우선)
- 주문/스티어링/쓰기 경로 **없음**. `steering/commands.jsonl` 등 데몬 입력 파일에 쓰는
  코드는 존재 자체가 금지. 쓰기는 SDK 경유 `viz-shell/src/generated/` 편집뿐.
- **정직한 환원 (critic 반영)**: viz-shell 자체 코드에 쓰기 경로가 없는 것과 별개로,
  실질적 쓰기 행위자는 SDK 서브프로세스다. 따라서 "읽기 전용 보장"은 FR-3의 경로 경계
  콜백이 유지되는지로 환원된다. 추가 방어:
  - `steering/commands.jsonl`은 데몬의 **조작 입력 채널**이며 토큰 스탬프로 보호된다 —
    viz-shell dev 서버는 **스티어링 토큰 env가 unset된 환경**에서 실행한다(SDK가 토큰을
    상속받을 수 없게).
  - **통합 테스트 필수**: SDK 설정 하에서 `steering/commands.jsonl` append 및
    `generated/` 밖 임의 경로 Write 시도가 거부됨을 검증하는 경계 거부 테스트.
- 쓰기/조작이 필요하면 기존 operator-console 사용(범위 외).

### NFR-2: 네트워크 노출 (SECURITY-07)
- dev 서버는 **127.0.0.1 바인딩**, 외부 인터페이스 노출 금지. 인증 계층 없음이 전제이므로
  localhost-only가 경계다 (F71 모바일 경로의 Tailscale 노출과는 별개 표면 — 통합 금지).

### NFR-3: SDK 권한 경계 (SECURITY-06/08/11)
- 최소 권한: 편집 가능 경로 allowlist(`viz-shell/src/generated/`), 도구 allowlist,
  `bypassPermissions` 금지, cwd=`viz-shell/`. 데몬 워킹트리(src/, workspace/, steering/)는
  SDK 쓰기 불가.

### NFR-4: 입력 검증 (SECURITY-05)
- 모든 tRPC procedure 입력은 zod 스키마 검증(경로 파라미터 화이트리스트 — 임의 경로 읽기
  금지, path traversal 차단).

### NFR-5: 로깅 (SECURITY-03)
- 채팅 요청/SDK 턴/라우터 오류를 서버 로그로 남김(민감값 비기록).

### NFR-6: 프로덕션 무영향
- 데몬 산출물 파일은 read-only로만 열기. 폴링 주기는 부하 무시 수준(수 초 단위).
- viz-shell 다운/오류가 데몬에 영향 줄 경로 없음(프로세스/파일 분리).

### NFR-7: 비용
- 뷰 생성 = Claude Code 1턴(구독 한도 내). 토큰 단위 별도 과금 없음.

## 4. 테스트 요구사항 (PBT Partial 반영)
- **PBT 대상(순수 함수/직렬화만)**: jsonl torn-line safe 파서(임의 바이트 절단 입력에도
  완전한 라인만 반환), zod 스키마 라운드트립(snapshot/equity 레코드 parse→serialize 불변).
  프레임워크: fast-check (bun test 위).
- 단위 테스트: 라우터(파일 픽스처 기반), 경로 화이트리스트 거부 케이스.
- 통합 검증: 실데이터 스모크(실 `steering/snapshot.json`·`workspace/equity.jsonl` 읽기) —
  Build & Test 단계.

## 5. 범위 외 (Out of Scope)
- 쓰기/스티어링 경로 일체 (operator-console 영역)
- 결정/턴·체결·시그널/헬스 라우터 (후속 확장 — 구조만 대비)
- 생성 뷰 자동 승격(방향 B), 뷰 품질 평가
- 모바일 노출(F71과 분리), 외부 네트워크 노출, 인증/멀티유저
- 데몬·launcher·operator-console 코드 변경

## 6. 결정 기록 (UAQ 2026-06-12)
| 질문 | 결정 |
|---|---|
| MVP 데이터 표면 | 포트폴리오 코어만 (snapshot + equity + positions) |
| SDK 인증 | claude CLI 구독 재사용 (~/.claude) |
| Security Baseline | Yes (blocking) |
| PBT | Partial (순수 함수/직렬화 라운드트립) |
| 브랜치/머지 정책 | `vibeshell` 장기 브랜치, 사용자 안정 선언 시에만 머지 |
