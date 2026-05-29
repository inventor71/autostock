# Tech-Stack 결정 — Unit B `operator-tool` (F4, opencode 하드 fork)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit B · NFR Requirements · 2026-05-30._

| 관심사 | 결정 |
|---|---|
| 베이스 | **opencode (`github.com/sst/opencode`, MIT)** 하드 fork — baseline commit/tag 핀, 업스트림 추적 안 함 |
| **콘솔 LLM / auth** | **비-Anthropic 모델(OpenAI GPT-5.5 류)을 콘솔 자체 OAuth로** 연결. **🚫 Claude 구독(OAuth) 절대 미사용** — third-party 사용은 ToS 위반·**계정 밴 → 트레이딩 agent까지 사망** 위험(우회 플러그인 금지). agent=Claude 구독, 콘솔=OpenAI OAuth로 **인증 분리**. NL→verb는 경량이라 비용·모델급 부담 작음. |
| 런타임/툴체인 | **Bun/TypeScript 전용 + OpenTUI(JSX 터미널 UI)** — 이 레포에 신규. ⚠ **Go 불필요**(스파이크 S0 정정: 현행 sst/opencode는 Go 0, 순수 TS/Bun; 이전 "Go/Bubble Tea" 가정 폐기) |
| TUI 확장 | **TuiPlugin API**(`packages/plugin/src/tui.ts`): `render`(JSX 패널)·`replace`(모달)·`toast`(알림) → 패널/확인모달/이벤트토스트를 플러그인으로(코어 깊은 수술 불필요, 'thin fork') |
| 도구 제거 지점 | `packages/opencode/src/tool/registry.ts`(단일) — task/shell/edit/write/webfetch import 제거 |
| 결정적 액션 | **MCP 서버 `steer`/`steer_read`**(stdio, `@modelcontextprotocol/sdk`) — *재설계 2026-05-30*: plugin Hooks.tool 대신 MCP. **opencode가 MCP 툴을 자동 게이트**(session/tools.ts:135 `ctx.ask({permission:"autostock_steer"})`)하므로 **confirm을 opencode 코어가 강제**(우리 코드가 ask 호출/유지 불필요 — plugin self-ask 실패모드 제거). 결정적 파싱/토큰/append는 `steer-handler`(parser/filedrop 재사용). plugin은 Phase 2 TUI 패널 전용. |
| 도구 봉쇄 | **컴파일타임 제거**: `task`/파일쓰기/edit/임의 bash/web 비등록 → side-effect=`steer`+읽기 only (#5894/#6396 구조적 불가) |
| 토큰 | `process.env.STEERING_OPERATOR_TOKEN`(Bun)에서 읽어 명령에 부착, 미표시 |
| file-drop I/O | TS로 repo-root `steering/` commands append(원자적)·events tail·snapshot read |
| 스키마 동기 | TS 타입 **수기 유지 + cross-language 계약 테스트**(Unit A pydantic이 권위) |
| 배포 | 브랜드 바이너리 `autostock-console`(또는 fork에서 bun/go 실행), 로컬 |
| 테스트 | bun test/vitest(파서·토큰·confirm) + 계약 테스트 + 컴파일타임 제거 검증 |
| 라이선스 | MIT 준수(고지 유지) |

## 신규 의존성 / 핀 (SECURITY-10)
- opencode baseline(commit/tag) + 그 TS/Go 의존성 전체를 lockfile로 핀. 플러그인 추가 deps도 핀.
- (Unit A는 0 신규 런타임 dep였음 — Unit B가 F4의 의존성/툴체인 무게를 진다.)

## 미해소(스파이크에서 확정 — 사용자 분기 아님)
- 정식 레포/태그(`sst/opencode` vs 리네임 이력) · custom tool 등록 API 현행 형태 · side-effect 도구 제거 지점 ·
  Go TUI 커스텀 pane 추가 방법 · 빌드/배포 파이프라인.

## 요약
Unit B는 **새 언어 deliverable(TS+Go) + 두 번째 LLM 런타임**. 무게는 코드 자체보다 **fork 소유·툴체인·스키마 상호운용·
컴파일타임 보안 봉쇄**에 있다. **fork-feasibility 스파이크**(nfr-requirements §6)로 미지수를 먼저 제거한 뒤 NFR Design 확정.
