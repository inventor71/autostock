# F28 — Normal-mode UI Self-Explanation 요구사항

> Track: **F28** · Type: feature · Brownfield · Depth: Minimal
> Source answers: `supervisor-ui-help-questions.md` (Q1–Q6 + Q2a/2b/2c, 2026-06-01~02)
> Security Baseline: **N/A** (Q5=B) · Property-Based Testing: **N/A** (Q6=C)
>
> **⚠️ 범위 단순화 (사용자 결정 2026-06-02):** critic 검토 후 복잡도 재평가 → **"최소: 의미만 정적
> 파일"** 채택. 당초의 (a) `data_source` 현재값 매핑, (b) TUI startup 자동생성, (c) fallback을
> **전부 제거**. 근거: ① 사용자는 화면에서 이미 값을 봄(질문은 "값이 얼마야"가 아니라 "이게 뭐야"=의미),
> ② "의미"는 UI 텍스트보다 안정적이라 정적 파일 + PR 규약으로 drift 충분히 관리, ③ 현재값 매핑은
> 오히려 monitor.json 구조와 새 결합·drift원을 만듦(critic HIGH#3). **변경 표면 = parent repo
> `operator-console/src/`만**(verb+handler+정적 json). 서브모듈·파이썬 데몬 변경 0.
> 무효화된 답변: Q2a/Q2b/Q2c/Q3/Q-FD2/Q-FD3/Q-FD4 (현재값·자동생성·fallback 전제) → 정적-의미 모델로 대체.

## 1. 의도 분석 (Intent Analysis)

- **User Request**: normal mode에서도 에이전트가 자기 TUI 요소(예: 타임라인 topbar `$6.01`, 마커 ◆/○/+/⧫, 사이드바 블록)의 의미를 설명할 수 있게 한다. 현재 에이전트는 daemon snapshot/`steer_read`에 그 데이터가 없어 "모른다"고 답함(스크린샷 증거).
- **근본 원인**: 에이전트는 **자기 TUI가 무엇을 그리는지** 모른다. 코드 접근은 normal mode에서 차단(F26). TUI 요소의 의미·데이터 출처를 코드가 아닌 별도 경로로 제공해야 함.
- **Request Type**: New Feature (지식 제공 레이어 — TUI 요소 → **정적 의미** 사전)
- **Scope (단순화 2026-06-02)**: Single Component, parent repo `operator-console/src/`만 — `steer_read`에 `/ui-legend [element]` read verb 추가(`parser.ts` + `steer-handler.ts`) + **정적 `ui-legend.json`**(사람 유지, git, 코드에 import 또는 read). **서브모듈·파이썬 데몬 변경 0.** (현재값 매핑·TUI 자동생성 제거 → MCP 프로세스 경계·monitor.json 결합 문제 모두 소멸.)
- **Complexity**: **Low** — verb 등록 + 정적 JSON 서빙. 코드 ~30줄 수준.

## 2. 현재 상태 근거 (코드 확인)

- `$6.01` 의미 = `today_cost_usd`: 타임라인 topbar는 F25(서브모듈)에서 `fmtCost(monitor.turns.today_cost_usd)`로 표시(`timeline-bar.tsx:70,128`, `use-monitor-data.ts:58` — critic 검증). **이 "의미"가 legend 항목으로 들어감**(현재값은 서빙 안 함 — 사용자가 화면에서 봄).
- **`steer_read` 계약**: inputSchema는 `{command: z.string()}` **단일 필드**(`mcp-server.ts:64`). verb는 `command` 문자열에 인코딩. legend는 **`steer_read{command:"/ui-legend [element]"}`** 새 read verb로 노출. **구현 선례 = F29 `/codebase` verb**(parser.ts:28 READ_VERBS + steer-handler.ts:112 분기 + mcp-server.ts:64 description). `handleSteerRead`가 정적 `ui-legend.json`을 `readFileSync`로 읽어 반환. 파이썬 데몬·`$STEERING_DIR`·`schema.ts` 미관여(READ_VERBS pseudo-verb는 SteeringVerb 아님 → golden contract 미변경).
- **에이전트 discovery (critic HIGH)**: `steer_read` description(`mcp-server.ts:58-65`)이 verb 목록을 하드코딩 — 에이전트가 verb 존재를 아는 유일한 경로(`/codebase`도 거기 추가됨). **`/ui-legend`를 description에 추가하는 것이 MANDATORY**(빠지면 사전을 만들어도 호출 안 됨).
- **권한 모델**: legend는 MCP 도구로 서빙되어 opencode 내장 `read` 권한과 무관. `autostock_steer_read`가 normal allowlist에서 이미 `allow`이므로 새 verb도 자동 허용 → **F26 권한 수정 0**.

## 3. 기능 요구사항 (Functional Requirements)

### FR-1 — 정적 UI Legend 파일 (사람 유지, git)
- **정적 `ui-legend.json`** 하나에 TUI 요소별 의미를 기술. parent repo `operator-console/src/` 내 고정 경로(예 `operator-console/src/ui-legend.json`)에 두고, `handleSteerRead`가 `readFileSync`(+try/catch)로 read (top-level `import`은 malformed 시 서버 crash → 금지, codebase 선례).
- 각 항목은 경량 JSON 객체:
  ```json
  {
    "id": "topbar.today_cost",
    "location": "타임라인 topbar, 날짜 네비게이션 오른쪽",
    "meaning": "오늘 에이전트 LLM 턴 비용 합계 (USD). 화면의 $ 값이 그 합계입니다."
  }
  ```
  - `id`(필수), `meaning`(필수), `location`(선택). **`data_source` 없음** — 현재값 매핑 제외.
- **Drift 관리(자동생성 대신 규약)**: UI를 바꾸는 PR에서 `ui-legend.json`도 함께 업데이트(리뷰어가 확인). "의미"는 UI 텍스트보다 안정적이라 정적 유지로 충분(사용자 판단 2026-06-02).

### FR-2 — MCP 서빙 (parent repo, `/ui-legend` verb) — F29 codebase 선례
3곳 수정 (모두 `operator-console/src/`):
1. `parser.ts`: `READ_VERBS`에 `ui-legend` 추가 (parser.ts:28 codebase처럼). **schema.ts 미변경.**
2. `steer-handler.ts`: `handleSteerRead`에 `if(draft.verb==="ui-legend")` 분기 (steer-handler.ts:112 codebase처럼). element는 `draft.args.raw`에서 split(READ_VERBS는 raw만 넘김).
3. `mcp-server.ts`: `steer_read` description에 `/ui-legend` 라인 추가 (**MANDATORY** — 에이전트 discovery).
- **element 인자**로 특정 요소만: `steer_read{command:"/ui-legend topbar.today_cost"}` → 해당 항목의 `{id, meaning, location}`.
- element 생략(`/ui-legend`) 시 전체 legend.
- 응답은 정적 의미만 (현재값 없음). 에이전트가 "화면의 $ 값은 오늘 턴 비용 합계예요"처럼 설명.

### FR-3 — 전체 TUI 커버리지 (Q4=A) — 의미만
정적 legend가 다룰 범위 (각 항목은 의미 텍스트):

| 영역 | 요소 예시 |
|------|----------|
| **Topbar** | 날짜 표시 (`2026-06-01 (Today)`), 날짜 네비 `[<] [>]`, `$X.XX` 비용(=오늘 턴 비용 합계) |
| **타임라인** | 시간 ruler (09:30–16:00), 마커 ◆(BUY)/○(SELL)/+(ADJUST_STOP)/⧫(HOLD) |
| **사이드바** | Account 블록(equity/cash/invested/open_pnl/positions), Positions, Round-trip summary, Recent fills |
| **상태줄** | RUNNING/HALTED/PAUSED, MKT(OPEN/CLOSED/PRE-MARKET) |

> 각 요소의 의미 텍스트는 Code Gen에서 F25/F6 TUI 코드를 읽어 정확히 작성(서브모듈은 변경하지 않고 *읽기만*).

### FR-4 — Normal-mode 접근성
- legend는 **MCP 도구 `steer_read`로 서빙** → opencode 내장 `read` 권한과 무관. `autostock_steer_read`가 normal allowlist에서 이미 `allow`이므로 새 verb도 자동 허용.
- 따라서 **F26 권한 수정 불필요**. (당초 "`$STEERING_DIR/**` read allowlist로 읽힌다"는 근거는 부정확 — 그 allowlist는 `read` 도구 직접 읽기에만 적용. MCP 서빙 경로와 무관.)
- F26 설계·allowlist **수정 없음**. (F28을 별도 트랙으로 분리한 핵심 이유 — Q1=A.)

### FR-5 — Drift 방지 메커니즘
- TUI가 startup 시 legend를 **매번 새로 생성**하므로, TUI 코드 변경 시 legend가 자동으로 따라간다.
- `data_source` 참조가 broken이면(bad pointer), **TS `handleSteerRead`**가 `current_value: null` + console warning. fail-open(의미는 표시, 값만 missing).
- 정적 fallback(서브모듈 assets)은 git-managed이므로, TUI 변경 PR에서 legend도 함께 업데이트되는 것이 권장 워크플로(리뷰어가 drift 발견 가능).

## 4. 비기능 요구사항 (NFR)

- **NFR-1 (데몬 매매 불변)**: 파이썬 매매 데몬 동작/계약은 변경 없음. **데몬·서브모듈 코드 변경 0** — 변경 표면은 parent repo `operator-console/src/`(verb+handler+정적 json)에 한정.
- **NFR-2 (토큰 비용 없음)**: system-prompt 주입이 아닌 MCP 도구 방식이므로, legend는 에이전트가 필요할 때만 가져간다. 평상시 토큰 비용 zero(Q2=C 배제한 핵심 이유).
- **NFR-3 (확장성)**: legend JSON 스키마는 추가 필드에 열려 있어야 한다(예: 향후 `examples`, `aliases`). `id`/`meaning`만 필수. 새 요소는 JSON 항목 추가만으로 커버.

## 5. 제약사항 (Constraints)

- **C-1**: F26 머지 이후에 유효함(normal에서 `autostock_steer_read` allow 필요). 현재 F26은 merged 상태이므로 충족.
- **C-2 (변경 표면 = parent repo만)**: `operator-console/src/{parser,steer-handler,mcp-server}.ts` (3곳 모두 필수 — mcp-server description은 MANDATORY) + 정적 `ui-legend.json`. **schema.ts·서브모듈·파이썬 데몬 미변경** → 서브모듈 브랜치 불필요(읽기만). worktree는 parent 브랜치 `feat/F28`.
- **C-3 (의미 정확성)**: legend 의미 텍스트는 Code Gen에서 F25/F6 TUI 코드를 *읽어* 정확히 작성. 서브모듈은 수정하지 않음.

## 6. 범위 밖 (Out of Scope)

- **현재값(실시간 수치) 서빙** — 사용자가 화면에서 봄. `data_source` 매핑 제외(2026-06-02 결정).
- **TUI startup 자동 legend 생성** — 정적 파일 + PR 규약으로 대체.
- TUI 코드 자체의 수정·신규 UI 요소 개발 (F25/F6 소관).
- supervisor mode를 위한 코드 전체 읽기 설명 (이미 F26으로 가능).
- UI legend를 system-prompt에 넣는 방식(Q2=C, 배제됨).

## 7. Extension Configuration

| Extension | Enabled | Rationale |
|-----------|---------|-----------|
| Security Baseline | No (Q5=B) | 읽기 전용 정적 UI 사전. 위험 표면 작음 (no secrets, no write path, no new network/runtime dep). |
| Property-Based Testing | No (Q6=C) | verb 파싱 + element 필터 단위 테스트로 충분. 무작위 속성 생성 불필요. |

## 8. 구현 단위

단일 응집 단위 `ui-legend` (parent repo): `parser.ts` verb + `steer-handler.ts` 분기 + 정적 `ui-legend.json` 작성.
