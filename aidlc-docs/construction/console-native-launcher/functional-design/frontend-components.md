# F5 Functional Design — Frontend Components (유닛 `console-native-launcher`)

> UI 변경은 모두 **기존 opencode 포크 컴포넌트 수정**(신규 화면 거의 없음). 경량 인벤토리.

## FC-1 — 로고 워드마크 (FR-2, Q1=B)
- 위치: `packages/opencode/src/cli/logo.ts` (`logo`/`go` 글리프), 렌더 `component/logo.tsx`(시머).
- 변경: "open"/"code" → **2줄 스택 "auto"/"stock"** 블록폰트. 시머 애니메이션/색 로직은 그대로.
- 검증: 좁은 폭에서 잘림 없이 표시, 시머 정상.

## FC-2 — 시작 화면 (FR-1, Q1/S2)
- 위치: `feature-plugins/home/{tips,footer}.tsx` + `plugin/internal.ts` 등록, 세션 뷰 진입 경로.
- 변경: 홈/스플래시(로고+"Ask anything"+팁) **우회** → 세션 뷰 직행.
- 검증: 켜자마자 세션, 입력/명령 흐름 정상.

## FC-3 — autostock 사이드바 기본 표시 (FR-1, S2)
- 위치: `feature-plugins/sidebar/autostock.tsx` (`sidebar_content()` 슬롯) + 키맵(`<leader>b`).
- 변경: **기본 표시(visible) 상태**로. 토글 보존.
- 검증: 시작 시 사이드바 보임, `<leader>b`로 끄고 켜짐.

## FC-4 — 런타임 끊김 배너 (FR-5, Q6=B)
- 위치: 사이드바/상단 영역(`RuntimeHealthSignal` E6 소비).
- 변경: MCP/채널 끊김 시 사람용 경고 라인(원인+조치, **비밀 미포함** BR-6). 복구 시 사라짐.
- 검증: 데몬/MCP 내려보고 배너 표출, 복구 시 해제.

## FC-5 — 리브랜딩 문자열 (FR-2, Q2=B)
- 위치: 푸터/스플래시/창 타이틀/팁/about 등 보이는 "opencode".
- 변경: → "autostock"(표기 일관). 비노출 식별자 제외.
