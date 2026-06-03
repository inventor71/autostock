# Business Logic Model — ui-legend

> Track: F28 · Unit: `ui-legend` · Depth: Minimal
>
> **범위 단순화 (사용자 2026-06-02):** 정적 의미 사전 서빙만. 변경 표면 = parent repo
> `operator-console/src/`. 서브모듈·파이썬 데몬 변경 0.
>
> **🔑 구현 선례 = F29 `/codebase` verb (critic 2차 검증).** `/ui-legend`는 `/codebase`와 구조적으로
> 동일하다: ① `parser.ts` READ_VERBS에 verb 추가(parser.ts:28의 `codebase`처럼) — **schema.ts
> `SteeringVerb`·`ALL_VERBS`·golden contract는 건드리지 않는다**(READ_VERBS 멤버는 `SteeringVerb`에
> 없고 parser.ts:77에서 `as SteeringVerb`로 캐스팅되는 콘솔 전용 pseudo-verb). ② `handleSteerRead`에
> `if (draft.verb === "ui-legend")` 분기 추가(steer-handler.ts:112의 codebase 분기처럼). ③ **MANDATORY:
> `mcp-server.ts`의 `steer_read` description(라인 58-65)에 `/ui-legend` 라인 추가** — 이게 에이전트가
> verb 존재를 아는 유일한 경로(`/codebase`도 line 64에 그래서 추가됨). 빠지면 사전을 만들어도 호출 안 됨.

## 컴포넌트 분담 (변경 표면)

| 측 | 위치 | 트래킹 | 역할 |
|----|------|--------|------|
| **사전** | `ui-legend.json` (정적) | `operator-console/src/` (**parent repo**) | TUI 요소별 의미. 사람 유지, git. |
| **서빙** | `parser.ts` (READ_VERBS), `steer-handler.ts` (분기), `mcp-server.ts` (description) | `operator-console/src/` (**parent repo**) | `/ui-legend` verb 등록 + legend read + element 필터 + 도구 description |
| **schema** | `schema.ts` | parent repo | **변경 없음** (READ_VERBS pseudo-verb는 SteeringVerb 아님 → golden contract 미관여) |
| **TUI** | `operator-console/cli/` | 서브모듈 | **변경 없음** (의미 작성 위해 *읽기*만) |
| **데몬** | `src/` | parent repo | **변경 없음** |

---

## BLM-1: Legend 작성 (정적, 사람)

- `ui-legend.json`을 사람이 작성 (Code Gen에서 초기 전체 TUI 커버 작성, F25/F6 코드 읽어 의미 확정).
- UI 변경 PR에서 함께 업데이트하는 **규약**으로 drift 관리 (BR-5). 자동생성 메커니즘 없음.

---

## BLM-2: Legend 서빙 (parent repo TS)

**Trigger**: 에이전트가 `steer_read{command:"/ui-legend"}` 또는 `steer_read{command:"/ui-legend <element>"}` 호출

**Flow** (전부 TS `handleSteerRead`, codebase 분기 선례):
```
steer_read{command:"/ui-legend topbar.today_cost"}
  │
  ├─► 0. parser.ts: parseCommand → READ_VERBS 분기(parser.ts:76-77)
  │      → {verb:"ui-legend", readOnly:true, args:{raw:"ui-legend topbar.today_cost"}}
  │      ⚠️ parser는 element를 split하지 않음 — READ_VERBS는 args:{raw}만 넘김(parser.ts:77).
  │         element 추출은 handleSteerRead 책임(아래 step 2).
  │
  ├─► 1. legend 로드 (handleSteerRead의 `if(draft.verb==="ui-legend")` 분기)
  │      - readFileSync(new URL("./ui-legend.json", import.meta.url)) + try/catch (BR-4)
  │      - ⚠️ top-level `import`은 malformed JSON에서 MCP 서버 spawn crash → 금지(BR-4).
  │        codebase 선례(steer-handler.ts:113-114): 파일 없으면 graceful 메시지.
  │
  ├─► 2. element 추출 + 필터 (BR-3, handler가 raw에서)
  │      - draft.args.raw를 split → head("ui-legend") 제거 → 나머지 = element
  │      - element 있으면 → entries 중 id exact match / 없으면 → 전체 entries
  │
  └─► 3. JSON.stringify({legend, error?}) 를 text로 반환
         (mcp-server.ts:69 content:[{type:"text", text}] — /turns·/codebase 패턴 동일)
```

현재값 해석·파일 fallback·프로세스 경계 문제 **없음** — 정적 파일 read + element 필터만.

---

## BLM-3: MCP 도구 계약

**Tool**: `autostock_steer_read` (기존 재사용 — 신규 도구 없음)
**inputSchema**: `{ command: z.string() }` (변경 없음)
**New read verb**: `/ui-legend [element]` (parser.ts READ_VERBS 등록, `readOnly:true` → mutating 아님 → opencode `ask` 게이트 없음)
**Description 갱신 (MANDATORY)**: `mcp-server.ts:58-65`의 `steer_read` description에 `LEGEND verb: /ui-legend [element] — TUI 요소(타임라인/사이드바/상태줄)의 의미. 화면 요소가 뭔지 물으면 이걸 써라.` 추가. 이게 빠지면 에이전트가 verb 존재를 몰라 호출하지 않음(critic HIGH#1).

**호출 예시**:
```
steer_read{command:"/ui-legend"}                    // 전체
steer_read{command:"/ui-legend topbar.today_cost"}  // 특정 요소
```

**응답**: LegendResponse(E3) JSON을 text로.

**에이전트 사용 흐름**:
```
사용자: "탑바에서 $6.01은 뭐야?"
에이전트: steer_read{command:"/ui-legend topbar.today_cost"}  (또는 /ui-legend 후 매칭)
        → "타임라인 topbar의 $ 값은 오늘 에이전트 LLM 턴 비용 합계예요. 지금 화면의 $6.01이 그 값입니다."
```

---

## BLM-4: 권한 모델

normal 모드에서 F26 권한 수정 없이 동작하는 이유:
- legend는 **MCP 도구 `steer_read`로 서빙** → opencode 내장 `read` 권한과 무관.
- `autostock_steer_read`가 이미 normal allowlist에서 `allow`(opencode.jsonc) → 새 verb 자동 허용.
- 정적 `ui-legend.json`은 MCP 서버 빌드에 포함(import)되거나 자기 경로 기준 read → `$STEERING_DIR` allowlist와도 무관.
