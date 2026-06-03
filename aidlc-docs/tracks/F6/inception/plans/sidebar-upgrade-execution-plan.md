# F6 — 콘솔 사이드바 업그레이드 · 실행 계획 (Workflow Planning)

- **트랙**: F6. 요구사항: `inception/requirements/sidebar-upgrade.md`.
- **리스크**: **Low–Medium** — read-only UI 변경 위주, 주문/스티어링/권한분리 경로 불변. 가장 큰 변경은
  사이드바 폭의 정적→반응형 전환과 메인 재레이아웃(콘솔 TS/SolidJS), 그리고 데몬 snapshot 페이로드 소폭 확장(Python).
- **베이스(Q4=A)**: `main`에서 독립 worktree+branch. F5(console-native-launcher)와 동일 파일 충돌 영역
  (사이드바 default-on, 리브랜드)은 **F6 범위에서 제외** → 충돌 표면 최소화. 머지 시 리베이스/조율.

---

## 1. 단계 결정 (Adaptive)

| 단계 | 실행 | 근거 |
|------|------|------|
| User Stories | **SKIP** | 단일 운영자 도구. 워크플로는 FR-1..5로 포착(F2~F5와 일관). |
| Workflow Planning | **EXECUTE** | (본 문서) |
| Application Design | **SKIP** | 신규 서비스/컴포넌트 경계 없음 → Functional Design으로 흡수. |
| Units Generation | **SKIP** | 단일 응집 단위. |
| **CONSTRUCTION — 단위 `console-sidebar-upgrade`** | | |
| Functional Design | **EXECUTE** | UI 컴포넌트(드래그 핸들/리사이즈 모델·계정/성과 블록·스타일) + 데이터 소싱 + FR-4 명령 경로 정의. UI라 [[feedback-ui-concretization]]에 따라 질문으로 구체화. |
| NFR Requirements | **EXECUTE (minimal)** | 기술스택 확인: **0 new runtime deps** 예상(OpenTUI 마우스 이벤트·stdlib fs·기존 snapshot/broker 재사용). 검증만. |
| NFR Design | **EXECUTE** | snapshot 페이로드 확장은 워커 스레드(NFR-2)·폴링 주기 유지; 폭 영속화 파일 I/O; fail-closed 표시; 보안(SECURITY-03/11/15) 배치. |
| Infrastructure Design | **SKIP** | 로컬 TUI/데몬, 인프라 없음. |
| Code Generation | **EXECUTE** | Part1 계획 → Part2 구현(worktree). |
| Build and Test | **EXECUTE** | TS bun 테스트 + tsgo 타입체크 + Python 무회귀(snapshot 확장 시) + 라이브 검증(드래그/표시). |

---

## 2. 단위 `console-sidebar-upgrade` — 내부 구현 순서

- **S1 — 폭 반응형화 + 드래그 리사이즈 (FR-1).**
  `routes/session/sidebar.tsx` `sidebarWidth()` 정적 읽기 → 반응형 width 상태(컨텍스트/시그널). 사이드바 경계에
  드래그 핸들(box) 추가, `onMouseDown`→`onMouseDrag(dx)`→`onMouseDragEnd`로 width 갱신, 24~터미널폭 클램프.
  `routes/session/index.tsx:243` `contentWidth` 메모가 반응형 width를 구독해 재레이아웃.
- **S2 — 폭 영속화 (FR-1.1, Q3=A).** 확정 폭을 콘솔 로컬 상태(파일/ tui config)에 저장, 시작 시 복원.
  우선순위 saved > `AUTOSTOCK_SIDEBAR_WIDTH` env > 42. (저장 위치 FD 확정.)
- **S3 — 계정 핵심지표 + 라운드트립 요약 발행 (FR-2/3).**
  데몬 `runtime.publish_snapshot`(이미 워커에서 `get_portfolio_state()` 호출)에 `equity`/`cash`/`open_pnl`/
  `position_count` 추가; 오늘 라운드트립 요약(승률/실현손익/건수)은 `src/core/trades.py match_round_trips` 재사용해
  발행(또는 콘솔 직접 trades.jsonl 읽기 — FD 확정). 콘솔 `autostock.tsx`가 새 필드 표시.
- **S4 — 가시성/스타일 (FR-5).** 섹션 헤더/구분, PnL 색상(테마 success/error), 숫자 정렬·강조, 빈 상태.
  기존 events 포맷 톤 유지. (default-on/폭 기본값은 F5 소유 → 손대지 않음.)
- **S5 — 온디맨드 읽기 명령 (FR-4).** 턴 텔레메트리/decisions/agent log를 슬래시/Read 명령으로 등록.
  메커니즘 FD 확정(opencode 슬래시 커맨드 vs read MCP 툴 — F4 NL-only 정착과 일관). 전부 read-only.
- **S6 — 테스트 + 재핀 + 라이브 검증.** bun 단위테스트(파서/소싱 헬퍼), tsgo 타입체크, snapshot 확장 시
  Python 무회귀; 서브모듈 `operator-console/cli` 변경 커밋+재핀; 드래그/표시/명령 라이브 확인(사용자).

---

## 3. F5 조율 (재확인)

- 동일 파일: `autostock.tsx`(F5=리브랜드/구조, F6=계정·PnL·스타일), `index.tsx`/`sidebar.tsx`(F5=sidebar-first,
  F6=폭 동적화). **F6는 default-on·리브랜드를 구현하지 않음**(F5 소유). 머지 순서 무관하게 양쪽이
  공존하도록 변경을 좁게 유지; 충돌 시 F6가 리베이스.

## 4. 산출물/추적

- Functional Design: `construction/console-sidebar-upgrade/functional-design/`.
- NFR: `construction/console-sidebar-upgrade/nfr-requirements/`, `…/nfr-design/`.
- Code Gen 계획: `construction/plans/sidebar-upgrade-code-generation-plan.md`.
- 진행은 `aidlc-state.md` F6 트랙 + 각 plan 체크박스에 즉시 반영.

## 5. 대안 (비권장)

- **2-unit 분리**(daemon-publish vs console-ui): 발행 확장이 작아 오버엔지니어링. 단일 단위 권장.
