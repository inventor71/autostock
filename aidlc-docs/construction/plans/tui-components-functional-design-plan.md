# Functional Design Plan — Unit B: tui-components (TypeScript)

## 유닛 컨텍스트
opencode 포크(Solid.js + OpenTUI)에 AI 협업 전용 UI를 구축한다.
타임라인 바(채팅 상단), 턴/심볼 호버 오버레이, monitor.json 폴링.

### 기술 환경 (탐색 결과)
- **프레임워크**: OpenTUI (`@opentui/solid` 0.2.16) — Solid.js 기반 터미널 UI, NOT React/Ink
- **플러그인 시스템**: 슬롯 기반 (`sidebar_content`, `app_bottom`, `app`); 현재 `session_top` 슬롯 없음
- **마우스**: `onMouseUp`/`onMouseDrag` 지원; 호버는 시그널 기반 시뮬레이션
- **오버레이**: `position="absolute"` + `zIndex`; `Dialog` 컴포넌트 참고
- **기존 폴링**: `feature-plugins/sidebar/autostock.tsx`에서 1.5s `setInterval`
- **상태 관리**: Solid.js `createSignal`/`createStore`

## 질문

---

## Question 1
타임라인 바의 상호작용 모델: 터미널에서 마우스 "호버"는 완전하지 않습니다.
`onMouseUp`(클릭)은 확실히 동작하지만, `onMouseMove`(호버)는 OpenTUI의 지원 수준에 따라 다릅니다.
어떤 상호작용을 기본으로 할까요?

A) **클릭 기반** — 마커를 클릭하면 오버레이 토글 (확실하게 동작). 호버가 되면 보너스
B) **키보드 기반** — 좌/우 화살표로 마커 선택, Enter로 오버레이 토글. 마우스는 보조
C) **양쪽 지원** — 클릭 + 키보드 양쪽 모두. 구현량 증가하지만 접근성 확보
X) 기타 (아래 [Answer]: 뒤에 설명해주세요)

[Answer]: A

---

## Question 2
타임라인 바의 레이아웃 위치: 현재 Session 뷰에는 `session_top` 슬롯이 없습니다.
타임라인 바를 어떻게 배치할까요?

A) **Session 레이아웃 직접 수정** — `routes/session/index.tsx`에 타임라인 바 영역을 추가 (메인 콘텐츠 위)
B) **새 플러그인 슬롯 추가** — Session 레이아웃에 `session_top` 슬롯을 만들고, 타임라인을 플러그인으로 등록
C) **기존 사이드바 상단에 배치** — 사이드바의 `sidebar_title` 슬롯 아래에 타임라인을 넣기 (가로 공간 제한적)
X) 기타 (아래 [Answer]: 뒤에 설명해주세요)

[Answer]: B

---

## Question 3
오버레이(턴 상세 / 심볼 논거)의 시각적 형태를 어떻게 할까요?

A) **플로팅 패널** — 클릭한 마커 근처에 `position="absolute"` + `zIndex`로 부유 패널 표시 (Dialog 패턴 활용, 크기 작게)
B) **사이드바 교체** — 오버레이 내용을 기존 사이드바 영역에 표시 (사이드바 임시 교체, 닫으면 원래로)
C) **하단 패널** — 채팅 영역과 프롬프트 사이에 접이식 패널로 오버레이 표시
X) 기타 (아래 [Answer]: 뒤에 설명해주세요)

[Answer]: A

---

## Question 4
심볼 오버레이(thesis viewer)에서 `positions/SYMBOL.md` 파일을 어떻게 읽을까요?

A) **직접 파일 읽기** — `fs.readFileSync`로 `workspace/positions/SYMBOL.md` 직접 읽기 (기존 사이드바 패턴과 동일)
B) **MCP 도구 경유** — 새 `steer_read thesis SYMBOL` 도구를 추가하고 MCP를 통해 읽기 (보안 경계 준수)
C) **monitor.json 확장** — daemon이 보유 심볼의 thesis 요약을 monitor.json에 포함 (daemon 변경 필요)
X) 기타 (아래 [Answer]: 뒤에 설명해주세요)

[Answer]: A

---

## Question 5
패키지 구조: 별도 패키지(`packages/tui-trading/`)로 분리한다고 하셨는데,
기존 feature-plugins와의 관계를 어떻게 할까요?

A) **별도 패키지 + feature-plugin 진입점** — `packages/tui-trading/`에 컴포넌트/훅 구현, `feature-plugins/`에 슬롯 등록용 엔트리 파일
B) **feature-plugins 폴더에만** — 별도 패키지 없이 `feature-plugins/timeline/` 폴더에 모든 파일 배치 (기존 패턴과 동일)
C) **완전 독립 패키지** — `packages/tui-trading/`에 모든 것 (컴포넌트 + 슬롯 등록 + 데이터 폴링)
X) 기타 (아래 [Answer]: 뒤에 설명해주세요)

[Answer]: C. 주식거래로 리브랜딩 되어있기에 C로 해도 괜찮을거라 생각했는데, 단점이 있다면 알려줘 (이거 먼저 토의하자.)

---
