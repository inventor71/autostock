# F5 Functional Design — Business Rules (유닛 `console-native-launcher`)

## 기동 / 에러 처리
- **BR-1 (fail-closed)**: 어떤 `blocking` 프리플라이트/데몬 단계 실패도 **명확한 한 줄 진단 + 해결법**을
  출력하고 **비-0 종료**한다. tool을 못 켠 채 조용히 끝나는 경로는 존재하지 않는다. (FR-5, NFR-2, SECURITY-15)
- **BR-2 (wedged 데몬)**: systemd 서비스가 `active`라도 `snapshot.json`이 `health_window`초 내로 신선하지
  않으면 "데몬이 떴지만 발행이 멈춤" 진단으로 처리(자동 start로 가리지 않음).
  - **BR-2.1 (health_window 튜닝 — critic #1, ✅코드확인)**: `publish_snapshot`은 직접 쓰지 않고 **단일 bus
    워커 큐**에 `_build`를 넣는다(`runtime.py:125`). 같은 워커가 executor 단계(`agent.py:58` `_funnel(timeout=
    180)`)와 in-flight 브로커 호출(~11s)에 점유되면 5s 주기여도 mtime이 수십 초 지연될 수 있다(콜드스타트의
    premarket research/open_execute 배치 포함). 따라서 `health_window`를 **5s 주기가 아니라 워커 최악 점유에
    맞춰 크게**(예: ≥30–45s) 잡고, 판정은 **bare mtime 단독이 아니라** snapshot의 `published_at` 변화 또는
    **연속 2회 신선 관측**으로 한다. (정확 상수는 NFR Design/Code Gen에서 확정.) `atomic_write_text`는 항상
    mtime을 갱신하므로(`jsonl.py:28-31`) 내용 불변이어도 신선도 판정 자체는 유효.
- **BR-3 (중복 기동 금지)**: 데몬이 이미 떠 있으면 `start`하지 않고 attach만 한다. 동시 실행/레이스 가드.
  - **BR-3.1 (health-first attach — 라이브 검증 발견, ✅수정 / critic 라운드3 정정)**: "이미 돌고 있나"의 **진짜 신호는
    systemd 상태가 아니라 fresh snapshot**이다. 데몬이 **systemd 밖(수동)으로** 떠 있을 수 있고(라이브에서 실제 그러함),
    그땐 `is-active`=inactive라 systemd만 보면 **둘째 인스턴스**를 띄워 같은 채널/브로커를 두 개가 건드린다.
    → 규칙: **snapshot이 fresh면 무조건 attach, 절대 start 안 한다.** advance-probe는 **정보용일 뿐 start를 좌우하지 않는다** —
    살아있는 데몬도 LLM 턴(premarket/intraday; APScheduler `max_instances=1`이 5s 발행을 분 단위로 굶김) 동안 발행이
    한참 안 올라갈 수 있어, "advance 없음 = 죽음"이 아니다(critic이 이 double-start 재발을 잡음). not-fresh일 때만
    systemd install+start(직전 isFreshNow 레이스 가드). **트레이드오프**: window(45s) 안에 막 죽은 데몬은 그 호출에서
    자동 재기동되지 않음 → 콘솔 끊김 배너(S6)로 표면화(둘째 기동보다 안전한 차선). post-start `healthWait`만 advance 요구.
- **BR-9 (start 레이스 가드)**: 두 `autostock`가 동시에 떠도 데몬은 한 번만 기동 — systemd가 단일 인스턴스를
  보장(같은 unit). 헬스-웨이트는 양쪽 모두 같은 snapshot 신선도를 본다.
  - **BR-9.1 (멱등 start — critic #1 sound)**: `is-active`→`start` 사이 TOCTOU로 두 인스턴스가 모두 `inactive`를
    보고 `systemctl --user start`를 호출해도, 이미 active한 unit에 대한 `start`는 **멱등 no-op**(에러 아님)이다.
    런처는 `start`를 멱등으로 취급하고 "already running"을 실패로 처리하지 않는다(잠재 버그 없음, ✅코드/systemd 동작).

## 데몬 수명 / systemd 정책
- **BR-4 (콘솔 독립 수명, Q3=A)**: 콘솔 TUI 종료가 데몬을 내리지 않는다. 데몬은 detached로 계속 트레이딩.
- **BR-5 (systemd 정책, Q2=A)**: user 유닛은 `Restart=on-failure` + 부팅/로그인 자동시작(`enable` + linger).
  최초 설치 시 1회 `ensure_installed`(유닛 생성·`daemon-reload`·`enable`·linger).

## 비밀 / 보안
- **BR-6 (토큰 비노출, Q7=A/SECURITY-03)**: 토큰 값은 화면/로그/배너/진단 어디에도 출력하지 않는다.
  표시 가능한 것은 존재 여부·일치 여부(boolean)뿐. 토큰은 메모리에서만 다루고 비교는 상수시간.
- **BR-10 (권한분리 불변, SECURITY-11/NFR-1)**: 콘솔/런처는 주문 권한이 없다(제안→사람 confirm→데몬
  RiskManager→Broker 게이트). agent 세션의 토큰 구조적 비접근 경계도 그대로. 본 유닛은 이 경계를 약화하지 않는다.
- **BR-11 (env 스코프)**: 런처가 콘솔로 주입하는 env는 콘솔 동작에 필요한 것만(STEERING_DIR/AUTOSTOCK_ROOT/
  토큰). 데몬 토큰을 agent 측에 흘리지 않는다(F4 env-scrub 유지).

## 계약 / 무회귀
- **BR-12 (계약 불변, NFR-4)**: `steering/` 파일드롭 계약(commands/events/snapshot/.cursor)과 Unit A 엔진은
  변경하지 않는다. "attach"는 같은 STEERING_DIR/토큰으로 채널을 공유하는 것 이상이 아니다.
- **BR-13 (무회귀, NFR-5)**: 기존 콘솔 기능(NL→MCP steer / 사이드바 / 락다운)과 파이썬 테스트 스위트는
  회귀 없이 유지. 파이썬 데몬 코드 변경 0을 목표(불가피하면 별도 게이트).

## UX / 리브랜딩
- **BR-7 (사이드바 우선, FR-1)**: 콘솔은 홈/스플래시를 거치지 않고 세션 뷰로 직행하며 autostock 사이드바를
  기본 표시한다. `<leader>b` 토글과 정상 입력 흐름은 보존한다.
  - **BR-7.1 (home-skip 메커니즘 — critic #3/critic2 #5, ✅코드확인)**: home은 토글 스플래시가 아니라 **기본 라우트**
    (`app.tsx:458`; session 라우트는 `--session/-c/-fork`로만 진입 `:495-521`). **critic2가 입증**: `sidebar_content`
    슬롯은 `session/sidebar.tsx:92`에서만 소비되고 세션 게이팅(`session/index.tsx:236`) → home(중앙 컬럼, side-region
    없음)에 사이드바를 얹는 건 **레이아웃 수술 + 세션 컨텍스트 의존**이라 라운드1의 "덜 침습" 전제가 뒤집혔다.
    **두 옵션(사용자 정책 결정)**: **(A)** `home.tsx` row-레이아웃 수술로 우측 패널 마운트, **(B, 추천·원래 Q1=A 의도
    "바로 세션 뷰로")** 부팅 시 세션 라우트 자동 진입(`-c`/합성 세션) → 기존 `sidebar_content` 경로 재사용. 택1은 정책
    답 후 Code Gen에서 라이브 검증.
  - **BR-7.2 (기본 표시 한정 — critic #5, ✅코드확인)**: opencode 사이드바 가시성은 `sidebar()=="auto" && wide()`
    (`routes/session/index.tsx:236-241`) — **넓은 터미널에서만 auto-표시**, 좁은 터미널·child(forked) 세션은 숨김.
    "기본 ON"은 "넓은 폭에서 auto"를 의미. 항상-표시를 원하면 `wide()` 게이트를 오버라이드해야 하나(좁은 폭 콘텐츠
    축소 부작용), 본 유닛은 **기존 auto 동작 유지**를 기본으로 한다.
- **BR-8 (런타임 경고, FR-5/Q6=B)**: 기동 후 MCP/채널 끊김을 감지하면 사이드바/배너로 경고한다(비밀 미포함).
- **BR-14 (리브랜딩 범위, FR-2/Q2=B)**: 로고는 2줄 스택 "auto"/"stock"(시머 유지), 사용자에게 보이는
  "opencode" 문자열은 전부 autostock으로 교체한다. 내부 비노출 식별자는 교체하지 않는다.
  - **BR-14.1 (provider-id 제외 — critic #2, ✅코드확인)**: 문자열 `"opencode"`는 사용자 노출 텍스트가 아니라
    **load-bearing provider-id 비교**로도 쓰인다 — `feature-plugins/home/tips.tsx:44`와 `feature-plugins/sidebar/
    footer.tsx:12`의 `item.id !== "opencode"`(무료모델/"connected" 판정). **이 리터럴은 치환 대상에서 제외**한다
    (무지성 전역 치환 시 connected 로직이 오판). 리브랜딩은 표면 문자열만, 식별자/비교 리터럴은 보존.
  - **BR-14.2 (대문자 타이틀 포함 — critic #2, ✅코드확인)**: 터미널 창 타이틀은 **대문자 "OpenCode" / "OC | …"**
    로 하드코딩(`cmd/tui/app.tsx:459,466,471,476`). 소문자 "opencode"만 쓸면 누락되므로 `visible_strings`에
    이 대문자 표기를 **명시적으로 포함**한다(→ "autostock" / "AS | …" 등 표기 일관).

## 설치
- **BR-15 (설치 위치, Q4=A)**: `autostock`는 `~/.local/bin/autostock`에 설치(sudo 불필요). 설치 시 해당 경로가
  PATH에 없으면 명확히 안내한다(조용한 미설치 방지 — BR-1 정신과 일관).
