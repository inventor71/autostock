# F5 — 콘솔 네이티브화 & 진입점 개선: 요구사항 명확화 질문

## 의도 분석 (요청 요약)

operator console(F4에서 만든 opencode 하드포크)를 **더 편하고 stock에 native하게** 업그레이드.
꼭 해야 하는 3가지:

1. **시작 화면**: 콘솔을 처음 켜면 지금은 opencode 홈/스플래시(애니메이션 "opencode" ASCII 로고
   + "Ask anything..." 프롬프트 박스 + 팁)가 먼저 뜸 → 처음부터 **autostock 사이드바가 보이는
   버전**으로 진입하고 싶음.
2. **로고**: "opencode" → **"autostock"** 으로 교체.
3. **진입점 교체**: 현재는 `cd operator-console/cli && bun dev`로 직접 들어감.
   대신 `claude`처럼 **바이너리/단일 명령**으로 띄우고, **데몬은 systemd로 관리**해서
   꺼져 있으면 **자동 기동**, 이미 돌고 있으면 **거기에 attach**.
   그리고 그 과정에서 잘못될 경우 **tool을 못 켜고 silent하게 종료**되는 일이 없도록 **에러 처리 개선**.

### 코드 기준점 (이미 확인함)
- 로고 글리프: `operator-console/cli/packages/opencode/src/cli/logo.ts`
  (`logo = {left:[...open...], right:[...code...]}`), 렌더는 `component/logo.tsx`(시머 애니메이션).
- 홈 화면(로고+"Ask anything"+팁): `feature-plugins/home/`.
- autostock 사이드바: `feature-plugins/sidebar/autostock.tsx` (현재 `<leader>b` 수동 토글, snapshot.json/events.jsonl 읽기 전용).
- 현재 실행: `cd operator-console/cli && bun dev`.
- 트레이딩 데몬: `python main.py --mode agent --steering` (repo-root `steering/` 채널로만 통신, 공유 토큰).
- **환경: WSL2** — systemd가 기본 활성화가 아닐 수 있음(`/etc/wsl.conf`의 `systemd=true` 필요). 항목 3에 영향.
- 보안 제약(기존): 콘솔은 주문 권한 없음(제안→사람 confirm→데몬 RiskManager→Broker 게이트), operator 토큰은
  agent 세션에서 구조적으로 접근 불가. 토큰은 비밀(로그/에러에 노출 금지 — SECURITY-03).

아래 질문에 `[Answer]:` 뒤에 보기 letter로 답해주세요. 맞는 게 없으면 `X) 기타` + 설명.

---

## Question 1 — 시작 화면 (사이드바 우선 진입)
콘솔을 처음 켰을 때 어떤 화면으로 진입할까요?

A) 홈/스플래시 화면을 **건너뛰고 바로 세션 뷰**로 들어가며 **autostock 사이드바가 기본으로 표시** (가장 native, 추천)
B) 홈 화면(로고/팁)은 **유지**하되 **사이드바만 기본 ON**
C) 홈 화면 유지 + 사이드바는 지금처럼 `<leader>b` 수동 토글 (현행 유지 — 변경 없음)
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A

---

## Question 2 — 로고/브랜딩 교체 범위
"opencode" → "autostock" 교체를 어디까지 할까요?

A) **홈 화면 ASCII 로고만** "autostock"으로 (현재 시머 애니메이션 효과는 유지)
B) ASCII 로고 + **눈에 보이는 "opencode" 문자열 전부**(푸터/스플래시/창 타이틀/about 등)까지 autostock으로 일괄 리브랜딩 (추천)
C) 애니메이션 빼고 **단순 텍스트 "autostock"** 으로 단순화
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: B

---

## Question 3 — systemd가 관리할 "데몬"의 대상
"데몬을 systemd로, 꺼져있으면 자동 기동, 돌고 있으면 attach" — 여기서 데몬은?

A) **파이썬 트레이딩 데몬**(`main.py --mode agent --steering`)을 systemd가 관리. **콘솔(바이너리)은 포그라운드 TUI**로 띄워 `steering/` 채널에 **attach**; 데몬이 꺼져 있으면 콘솔 기동 시 **자동으로 데몬을 켬** (추천)
B) **콘솔 자체**를 데몬화(백그라운드 서비스)하고 거기에 붙는 구조
C) **둘 다** 각각 서비스로 (트레이딩 데몬 + 콘솔 백엔드)
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A

---

## Question 4 — 프로세스 관리자 (WSL2 환경 고려)
데몬 자동 기동/관리를 무엇으로 구현할까요? (WSL2는 systemd가 꺼져 있을 수 있음)

A) **systemd user 서비스**(`systemctl --user`)만 사용 — WSL2 systemd 활성화 가정, 없으면 명확한 에러로 안내
B) **systemd 우선, 미지원/비활성 시 portable 폴백**(PID 파일 + 백그라운드 프로세스 supervise)으로 **자동 대체** — 어느 환경에서도 동작 (추천)
C) **systemd 없이 portable 자체 supervisor만** (PID 파일/헬스체크) — 의존성 최소화
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A. 만약 systemd 활성화에 문제가 있으면 그때 재결정.

---

## Question 5 — 진입 바이너리 형태 ("claude처럼")
`autostock` 명령으로 띄우는 진입점을 어떤 형태로?

A) **`autostock` 단일 명령을 PATH에 설치**(설치 스크립트). 내부적으로 프리플라이트 점검 후 콘솔을 실행하는 **얇은 런처**(bun 런타임 사용). `claude`처럼 어디서든 `autostock` 한 줄로 실행 (추천)
B) **`bun build --compile`로 진짜 단일 실행 바이너리**를 빌드해 설치 (런타임 비의존, 단 포크 전체 컴파일 부담/취약성 있음)
C) 현행 `bun dev` 유지하되 **래퍼 스크립트**만 추가 (최소 변경)
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A

---

## Question 6 — 기동 프리플라이트 / 에러 처리 범위 (silent 종료 방지)
"tool 못 켜고 silent 종료" 방지를 위한 점검/표시 범위는?

A) **기동 전 프리플라이트**: 토큰 일치 여부 / `STEERING_DIR` 존재 / 데몬 헬스(채널 응답) / MCP 서버 경로 해석 가능 여부를 점검 → 실패 시 **명확한 한 줄 진단 + 해결 방법** 출력, **절대 silent exit 안 함**
B) A + **런타임 중**에도 MCP/채널 끊김을 감지하면 사이드바/상단 배너에 경고 표시 (추천)
C) 최소한만 (데몬 기동 여부 정도만 확인)
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: B

---

## Question 7 — 토큰/비밀 취급 (에러·로그 노출 금지)
프리플라이트/에러 메시지에서 operator 토큰 등 비밀 취급 정책은?

A) 진단/로그에 **토큰 값은 절대 미출력**(존재 여부·일치 여부만 표시), 실패 메시지에서도 마스킹 — SECURITY-03 준수 (추천)
B) 디버깅 편의를 위해 토큰 일부 노출 허용 (비권장)
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A

---

## Question 8 — 확장(extensions) 적용
이 트랙에 적용할 확장 설정은?

A) **프로젝트 기본값 유지** — Security Baseline = Enabled(특히 SECURITY-03 비밀 비노출 / SECURITY-11 권한분리 유지 / SECURITY-15 fail-closed 기동: 프리플라이트 실패 시 안전하게 중단+안내). Property-Based Testing은 이 트랙(런처/TS UX)엔 대체로 N/A, 결정성 파서 등 순수 함수에만 선택 적용 (추천)
X) 기타 (아래 [Answer]: 뒤에 설명)

[Answer]: A
