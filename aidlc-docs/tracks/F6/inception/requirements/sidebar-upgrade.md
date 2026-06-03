# F6 — 콘솔 사이드바 업그레이드 · 요구사항

- **트랙**: F6 (신규 기능). F4 operator-console(opencode 하드포크)에서 deferred된
  "사이드바 마우스 드래그 리사이즈"(aidlc-state.md line 748)를 실현 + 가시성 + monitor.sh 역할 일부 이전.
- **깊이**: Standard. **유형**: 사용자 대면 TUI (운영자 콘솔). **리스크**: Low–Medium (read-only UI;
  주문 경로/권한분리 불변 — 안전 아키텍처 무변경).
- **승인된 답변(2026-05-30)**: Q1=A+E(사이드바) / B·C·D=slash 명령, Q2=A(가독성/스타일), Q3=A(폭 영속),
  Q4=A(main worktree 독립), Q5=A(확장 기본 유지).

---

## 1. 의도(Intent)

운영자가 콘솔 사이드바만 보고도 **계정 상태·성과·에이전트 상황을 한눈에** 파악하고, **폭을 마우스로 자유롭게**
조절하며, 더 깊은 모니터링(턴 비용/의사결정/로그)은 **온디맨드 명령**으로 꺼내볼 수 있게 한다.
현재 `monitor.sh`가 tmux 4-pane로 하던 모니터링을 콘솔 안으로 흡수해, 별도 tmux 대시보드 의존을 줄인다.

비목표(Non-goals): 주문/스티어링 경로 변경 없음(F4 NL-only + RiskManager→Broker 게이트 불변),
권한분리(SECURITY-11) 불변, Python 데몬 안전 로직 변경 없음. F5의 리브랜드/런처/사이드바-default-on과 **중복 구현 금지**(조율).

---

## 2. 기능 요구사항 (FR)

### FR-1 — 마우스 드래그 리사이즈
- 사이드바 경계(메인 콘텐츠와 맞닿는 가장자리)에 **드래그 핸들**을 두고, `onMouseDown`→`onMouseDrag`→`onMouseDragEnd`
  로 폭을 실시간 조절한다. OpenTUI가 해당 이벤트를 지원함은 확인됨.
- 폭은 **반응형(signal)** 으로 전환한다(현재 `sidebarWidth()`는 렌더 시 1회 정적 env 읽기 → 동적화 필요).
- **범위 제약**: 현행 24~120(터미널 폭에 맞춰 상한 클램프). 메인 콘텐츠 폭 계산(`index.tsx:243`
  `contentWidth = dimensions().width - sidebar - 4`)이 폭 변화에 따라 재레이아웃되어야 한다.
- **FR-1.1 영속성(Q3=A)**: 드래그로 확정된 폭을 저장하고 다음 실행에 복원한다. `AUTOSTOCK_SIDEBAR_WIDTH` env는
  **초기 기본값**으로만 작동(저장값 > env > 42 우선순위). 저장 위치/형식은 Functional Design에서 결정
  (후보: 콘솔 측 로컬 상태 파일; 시크릿 아님이라 권한 영향 없음).

### FR-2 — 사이드바에 계정 핵심지표 추가 (Q1=A)
- equity / 현금(cash) / **일일 PnL** / **누적(또는 실험-시작 이후) PnL**을 사이드바 상단부에 요약 1블록으로 표시.
- 데이터 출처: `monitor.sh`의 `status.py`가 보던 계정 상태. **조달 경로는 Functional Design에서 결정** —
  데몬이 `STEERING_DIR/snapshot.json`(이미 1.5초 폴링 중)에 계정 요약 필드를 **추가 발행**하는 방식 우선
  (콘솔이 broker를 직접 만지지 않음 → 권한분리·NFR 유지). snapshot에 없는 값은 발행기(`publish_snapshot`) 확장.

### FR-3 — 사이드바에 청산 라운드트립 요약 추가 (Q1=E)
- 오늘(ET-date) **승률 / 실현손익 / 청산 건수**를 1~2줄 요약. snapshot 확장으로 발행.
- **[critic #1 HIGH 반영 — 사용자 결정 B] 장중 정확도**: `trades.jsonl`은 장마감(`_eod`)에만 갱신되므로(`agent.py:133`)
  파일 읽기만으로는 장중 내내 빈 값이다. 따라서 **워커가 저빈도로 fills/activities를 집계**해 오늘 실현손익을 산출한다
  → "broker 추가호출 0" 단정은 폐기(저빈도 호출 1종 추가). 라운드트립 매칭은 `src/core/trades.py match_round_trips` 재사용.
- **[critic #4 MED] ET-date 변환**: fill `filled_at`은 UTC(`trades_log.py:64`)이므로 `zoneinfo("America/New_York")`로
  변환해 ET-date를 산출(UTC 자정/DST 경계 오집계 방지).
- **[F3 정렬]** F3 intraday-redesign이 이미 `get_fills`(Alpaca activities) 브로커 포트를 설계함. F6는 **그 포트와
  정렬/공유**(F6가 먼저 코딩하면 같은 포트를 구현, F3가 재사용). 중복 구현 금지 — Functional/NFR Design에서 명시.

### FR-4 — 깊은 모니터링은 온디맨드 읽기 명령으로 (Q1: B·C·D)
- **사이드바에 상주시키지 않고**, 운영자가 필요할 때 호출하는 읽기 명령으로 등록:
  - **턴 텔레메트리** (turns.jsonl: 최근 턴 비용/활동, 오늘 누적 턴 수/비용)
  - **최근 decisions** (decisions.jsonl: 최근 N건)
  - **agent log tail** (logs/autostock.log 최근 N줄)
- **메커니즘은 Functional Design에서 결정**. 후보: (a) opencode 슬래시 커맨드 파일, (b) 기존 read 경로(`steer_read`
  /MCP read 툴, F4가 NL-only로 정착) 확장. 모두 **read-only**이며 주문 권한과 무관. 사용자 표현은 "slash command",
  실제 구현은 F4의 정착된 읽기 채널과 일관되게 맞춘다.

### FR-5 — 가시성/가독성 강화 (Q2=A)
- 섹션 구분(헤더/구분선), **PnL 색상(+초록 / −빨강)**, 숫자 정렬·강조, 빈 상태("no positions" 등) 표시.
- 기존 events 포맷(글리프+`wrapMode="word"`)과 톤 일관. 테마 색(`api.theme.current`) 사용.
- 참고: "항상 표시/기본 폭"(Q2 B안)은 **F5가 처리** → F6는 스타일에 집중, 중복 구현 금지.

---

## 3. 비기능 요구사항 (NFR)

- **NFR-1 (권한분리 불변)**: 콘솔은 read-only 표시만. 주문/스티어링은 기존 NL→confirm→token→file-drop→
  RiskManager→Broker 게이트로만. 신규 모니터링/명령은 어떤 쓰기 권한도 부여하지 않음 (SECURITY-11).
- **NFR-2 (시크릿 비노출, SECURITY-03)**: 계정/턴/로그 표시·진단에서 operator token 등 시크릿을 출력/로그 금지.
- **NFR-3 (성능)**: 콘솔은 파일 **읽기 폴링 1.5초**(`autostock.tsx:142`); 데몬 **발행은 5초**(`agent.py:181`
  `publish_snapshot`) — [critic #6 LOW] 두 주기 구분. account 필드는 기존 발행에 가산. **라운드트립 fills 집계는
  더 느린 주기**(예: 30~60초 별도 잡)로 broker activities 호출 부하를 제한.
- **NFR-4 (무회귀)**: 기존 사이드바 내용/이벤트 표시, F4 contract(E7/E8/snapshot), Python 데몬 동작 불변.
  Python 테스트 스위트 회귀 없음(데이터 발행 확장 시에만 영향).
- **NFR-5 (fail-closed UX, SECURITY-15)**: snapshot 누락/파싱 실패 시 현행처럼 안전 폴백(빈 표시), 콘솔 비충돌.

---

## 4. F5 조율 (Q4=A)

- F5(console-native-launcher)는 `autostock.tsx`(사이드바 default-on)·리브랜드·런처를 **FD 승인 게이트**에서 진행 중.
  F6는 `routes/session/sidebar.tsx`(폭 동적화), `routes/session/index.tsx`(contentWidth 재레이아웃),
  `feature-plugins/sidebar/autostock.tsx`(계정/PnL/스타일)와 **겹친다**.
- **결정**: F6는 `main`에서 독립 worktree로 분기. 머지 시점에 F5와 충돌 조율/리베이스.
  중복 영역(사이드바 default-on, 리브랜드)은 F6 범위에서 **제외**(F5 소유)하여 충돌 표면 최소화.

---

## 5. 확장(Extensions) — 프로젝트 기본 (Q5=A)

- **Security Baseline = Enabled.** 적용: SECURITY-03(토큰/시크릿 로그·화면 노출 금지, FR-2/4 진단),
  SECURITY-11(권한분리 불변), SECURITY-15(fail-closed 표시). 그 외 대부분 N/A(웹/DB/IaC/auth 없음, 로컬 TUI).
- **Property-Based Testing = N/A(주)**. F6는 TS UI 위주. 단 데몬 측 계정/라운드트립 요약 발행에 **순수 함수**가
  생기면 부분 적용 검토(예: 라운드트립 집계는 기존 `match_round_trips` 재사용 → 신규 순수 로직 최소).

---

## 6. 미해결/Functional Design로 이월

1. 폭 영속성 저장 위치/형식 (콘솔 로컬 상태 파일 vs tui config).
2. 계정/라운드트립 요약 조달: `publish_snapshot` 필드 확장(권장) vs 콘솔 직접 파일 읽기.
3. FR-4 명령 메커니즘: opencode 슬래시 커맨드 vs read MCP 툴 확장(F4 NL-only 정착과 일관성).
4. 드래그 핸들 UX 디테일(핸들 위치/표식, 키보드 대체 단축키 필요 여부).
