# F6 — console-sidebar-upgrade · Functional Design 질문

> 요구사항: `inception/requirements/sidebar-upgrade.md`. 실행계획: `inception/plans/sidebar-upgrade-execution-plan.md`.
> `[Answer]: A` 태그로 답해 주세요. 모두 권장안 있음.

## 확정된 구현 사실(코드 대조)

- 사이드바는 화면 **오른쪽**(레이아웃 `contentWidth = dims.width − sidebar − 4`) → 드래그 핸들은 **사이드바 좌측 경계**.
- OpenTUI `MouseEvent`: 절대 `x`/`y`(열/행) + `button` + `isDragging` → 드래그 시 `width = dims.width − e.x`(클램프).
- 계정 equity/cash는 **데몬 broker에만** 존재 → 콘솔에서 직접 불가 → snapshot 발행 확장이 사실상 필수.
- `runtime.publish_snapshot`는 이미 워커 스레드에서 `get_portfolio_state()` 호출(NFR-2) → 필드 추가가 깨끗함.

---

## Q1. 드래그한 폭의 **영속 저장 위치/형식**은?

A. **콘솔 전용 사용자 상태 파일** (XDG, 예: `~/.config/autostock-console/ui.json` 또는 state 디렉터리). 머신-로컬, 깔끔 — **권장**
B. opencode **tui config**(`.opencode/tui.json`)에 `sidebarWidth` 필드 추가 (기존 콘솔 설정과 한 곳)
C. repo-내 프로젝트-로컬 파일(`operator-console/` 하위) — 단, 머신마다 다른 선호가 repo에 섞일 수 있음(비권장)

[Answer]: A

---

## Q2. 계정 지표 + 라운드트립 요약 **데이터 소싱**은?

A. **둘 다 `publish_snapshot` 확장**으로 (equity/cash/open_pnl/position_count + 오늘 승률/실현손익/건수). 단일 read-view·일관성 — **권장**
B. **account만 snapshot**, 라운드트립은 **콘솔이 `trades.jsonl` 직접 읽기**(데몬 변경 최소, 단 콘솔이 workspace 파일 접근 확대)

[Answer]: A

---

## Q3. FR-4 깊은 모니터링(턴 텔레메트리 / 최근 decisions / agent log tail) **명령 메커니즘**은?

A. **read MCP 툴 확장** (예: `autostock_read{view}`) — F4 NL-only/MCP 정착과 일관, opencode CORE 게이트(read=allow). 데몬이
   해당 요약을 `steering/` read 파일로 발행 → 콘솔/MCP가 contract 경계 안에서 읽음 — **권장**
B. **opencode 슬래시 커맨드 파일** — 사용자 표현 "slash command"에 가장 충실하나, 슬래시는 LLM 프롬프트로 확장됨(결정성↓)
C. **A + B 둘 다** (MCP read 툴 + 얇은 슬래시 래퍼)

[Answer]: A

---

## Q4. 드래그 핸들 **UX**는?

A. 사이드바 좌측에 **얇은 핸들(│)** 표시 + 드래그 리사이즈. 키보드 대체 없음 — 단순, **권장**
B. 핸들 + **키보드 단축키**(예: `Ctrl+←/→`로 폭 증감)도 함께 제공
C. 핸들 표식 없이 경계 영역 자체가 드래그 가능(미니멀)

[Answer]: A
