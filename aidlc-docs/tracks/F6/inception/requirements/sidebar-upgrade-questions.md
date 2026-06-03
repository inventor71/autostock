# F6 — 콘솔 사이드바 업그레이드 · 요구사항 질문

> 대상: F4 operator-console(opencode 하드포크)의 autostock 사이드바.
> 요청 3축: **(1) 마우스 드래그 리사이즈, (2) 가시성 확보, (3) scripts/monitor.sh 역할 일부 이전.**
> 작성 규칙: 각 질문에 `[Answer]:` 태그로 답해 주세요. 보기 외 의견은 `Other`에 자유 기술.

---

## 배경(현재 코드 기준, 사실 확인됨)

- 사이드바 폭: `routes/session/sidebar.tsx:15` `sidebarWidth()` — **고정 42**, `AUTOSTOCK_SIDEBAR_WIDTH`(24~120) env 오버라이드만 존재.
  코드 주석에 *"A proper mouse-drag resize is deferred to a separate feature"* 라고 명시 → 이 트랙이 그 deferred feature.
- 사이드바 내용: `feature-plugins/sidebar/autostock.tsx` — run-state/market, positions(+locked), open-orders,
  pending 수, queued trades, 최근 events 5줄(사람-친화 포맷). `STEERING_DIR/snapshot.json` + `events.jsonl` 1.5초 폴링, read-only.
- OpenTUI(이 포크)는 `onMouseDown/onMouseDrag/onMouseDragEnd/onMouseDrop/onMouseMove/onMouseUp` 지원 확인 → **드래그 리사이즈 구현 가능**.
- `scripts/monitor.sh`의 tmux 4-pane 담당: ① decisions.jsonl 라이브 ② account dashboard(`status.py` equity/현금/포지션/PnL)
  ③ agent log tail(`logs/autostock.log`) ④ turns+trades 텔레메트리(턴별 비용/활동 + 청산 라운드트립).
- **주의(F5 충돌):** 진행 중인 F5(console-native-launcher)가 같은 파일(`autostock.tsx`, 사이드바 기본 표시, 리브랜드)을
  Functional Design 승인 게이트에서 건드리는 중. 베이스/순서 조율 필요(Q4).

---

## Q1. `monitor.sh`에서 사이드바로 **가져올 정보**는? (복수 선택)

A. **계정 대시보드 핵심지표** — equity / 현금 / 일일 PnL / 누적 PnL (monitor.sh의 `status.py` 요약)
B. **턴 텔레메트리** — 최근 턴 비용/활동, 오늘 누적 턴 수/비용 (turns.jsonl)
C. **최근 decisions 스트림** — 최근 의사결정 N줄 (decisions.jsonl) ※ events와 별개
D. **agent log tail** — `logs/autostock.log` 최근 몇 줄
E. **청산 라운드트립 요약** — 오늘 승률/실현손익 (trades.jsonl)

[Answer]: A + E (사이드바). **B/C/D(턴 텔레메트리·decisions·agent log)는 사이드바에 넣지 말고 slash command(온디맨드 읽기 명령)로 등록.**

---

## Q2. "가시성 확보"의 의미는? (단일, 보완은 Other)

A. **가독성/스타일 강화** — 섹션 구분선·헤더, PnL 색상(+초록/−빨강), 숫자 정렬/강조, 빈 상태 표시
B. **항상 표시 + 충분한 기본 폭** — 단, F5가 이미 사이드바 default-on을 처리 중이라 중복 가능
C. **A + B 모두**
D. **스크롤/우선순위** — 정보가 많아질 때 중요한 것 위로, 나머지는 스크롤

[Answer]: A — 가독성/스타일 강화

---

## Q3. 드래그로 바꾼 폭의 **영속성**은?

A. **재시작 후에도 기억** — 폭을 상태/설정 파일에 저장하고 다음 실행에 복원
B. **세션 한정** — 재시작 시 기본값(또는 `AUTOSTOCK_SIDEBAR_WIDTH`)로 리셋
C. env 기본값은 유지하되 드래그 값이 그 세션 동안만 우선

[Answer]: A — 재시작 후에도 기억(영속)

---

## Q4. **F5와의 작업 베이스/순서** 조율은? (F5는 아직 미머지, FD 게이트)

A. **F5와 독립적으로 `main`에서 worktree 분기** 후 진행, 머지 시 조율/리베이스
B. **F5 브랜치 위에 쌓기** (F5 먼저 진행한다는 전제)
C. **F5가 끝날 때까지 F6는 설계만** 하고 코드 착수는 대기

[Answer]: A — main에서 독립 worktree 분기, 머지 시 조율/리베이스

---

## Q5. 확장(Extensions) 설정 — 프로젝트 기본 유지?

A. 프로젝트 기본 유지 — Security Baseline Enabled(여기 적용: SECURITY-03 토큰/시크릿 로그 노출 금지,
   SECURITY-11 권한분리 불변, SECURITY-15 fail-closed), PBT는 대부분 N/A(TS UI). 
B. 변경하고 싶음 (Other에 기술)

[Answer]: A — 프로젝트 기본 유지 (대화형 게이트에서 미제시, 기본값으로 확정; 변경 의견 없으면 A).
