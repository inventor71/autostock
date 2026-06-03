# F48 사이드바 정리 — Requirements

## Intent Analysis
- **User Request**: 사이드바에서 불필요한 요소(경로, LSP, 세션ID, Greeting)를 제거하고, OpenCode 브랜딩을 AutoStock으로 변경하며, Context를 한 줄로 축약
- **Request Type**: Enhancement (UI 정리)
- **Scope**: Single Component — operator-console TUI sidebar (5~6개 파일)
- **Complexity**: Simple — 대부분 삭제/텍스트 변경

## Functional Requirements

### FR-1: 사이드바 하단 경로 표시 제거
- **대상**: `sidebar/footer.tsx` — `path()` 계산 (lines 17-26) + 렌더링 (lines 63-66)
- **변경**: 경로 줄 (`parent/name`) 제거. 하단에는 AutoStock 브랜딩만 남김.

### FR-2: OpenCode → AutoStock 브랜딩 변경
- **대상**:
  - `sidebar/footer.tsx` lines 67-72: `• OpenCode {version}` → `• AutoStock {version}`
  - `sidebar.tsx` lines 118-124: 같은 브랜딩 텍스트 (default slot fallback)
- **변경**: "OpenCode" → "AutoStock", "Open" + "Code" 분리 표시 → "AutoStock" 단일 표시

### FR-3: LSP 사이드바 플러그인 제거
- **대상**:
  - `sidebar/lsp.tsx` — 파일 삭제 또는 미사용 처리
  - `plugin/internal.ts` — `SidebarLsp` import 제거 + 등록 배열에서 제거
  - `routes/session/footer.tsx` line 70 — LSP 카운트 표시 제거
  - `component/dialog-status.tsx` lines 96-119 — 상태 다이얼로그 LSP 목록 제거
- **변경**: LSP는 트레이딩 콘솔에서 불필요하므로 모든 LSP UI 요소 제거

### FR-4: Context 탭 한 줄로 축약
- **대상**: `sidebar/context.tsx`
- **변경**: 현재 3줄(tokens / % used / $ spent) → 1줄(토큰 + 비용 + used % 통합)
- **형식 예시**: `12,345 tokens · 48% used · $0.42 spent`

### FR-5: 사이드바 상단 세션ID 해시 제거
- **대상**: `sidebar.tsx` lines 87-89 — `<Show when={InstallationChannel !== "latest"}>` 블록
- **변경**: 세션ID 해시(`ses_1727e25a...`) 표시 제거. 세션 타이틀은 유지.

## Non-Functional Requirements

### NFR-1: 기존 기능 보존
- Autostock 트레이딩 사이드바(`autostock.tsx`)는 변경 없음
- 세션 타이틀, 워크스페이스 라벨, MCP/Todo/Files 사이드바 플러그인은 그대로 유지

### NFR-2: 빌드 무결성
- TypeScript 컴파일 오류 없어야 함
- 기존 테스트 통과 유지

## Files to Modify
| 파일 | 변경 내용 |
|------|-----------|
| `packages/opencode/src/cli/cmd/tui/feature-plugins/sidebar/footer.tsx` | 경로 표시 제거 + 브랜딩 변경 |
| `packages/opencode/src/cli/cmd/tui/routes/session/sidebar.tsx` | 세션ID 해시 제거 + 기본 브랜딩 변경 |
| `packages/opencode/src/cli/cmd/tui/feature-plugins/sidebar/context.tsx` | 3줄→1줄 축약 |
| `packages/opencode/src/cli/cmd/tui/feature-plugins/sidebar/lsp.tsx` | 파일 삭제 |
| `packages/opencode/src/cli/cmd/tui/plugin/internal.ts` | LSP import/등록 제거 |
| `packages/opencode/src/cli/cmd/tui/routes/session/footer.tsx` | LSP 카운트 제거 |
| `packages/opencode/src/cli/cmd/tui/component/dialog-status.tsx` | LSP 목록 제거 |
