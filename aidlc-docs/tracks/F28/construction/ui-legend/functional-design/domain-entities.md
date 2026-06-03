# Domain Entities — ui-legend

> Track: F28 · Unit: `ui-legend` · Depth: Minimal
>
> **범위 단순화 (사용자 2026-06-02):** 정적 의미 사전만. `data_source`/현재값/TUI 자동생성/fallback 제거.
> 서빙=parent repo `operator-console/src/` (`steer_read` `/ui-legend` verb). 서브모듈·파이썬 데몬 변경 0.

## Entity Overview

```
UiLegend ── entries: UiLegendEntry[]
                       ├── id: str (PK, 필수)
                       ├── meaning: str (필수)
                       └── location?: str (선택)
```

정적 JSON 파일 하나. 런타임 상태·해석·매핑 엔티티 없음.

---

## E1: UiLegendEntry

TUI 요소 하나의 의미를 기술하는 정적 항목.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | **Yes** | Unique identifier. dot-hierarchy 권장: `"topbar.today_cost"`, `"timeline.marker.buy"`, `"sidebar.account.equity"`. element 쿼리의 키. |
| `meaning` | `string` | **Yes** | 한국어 설명문. 에이전트가 사용자에게 그대로 보여줄 문장. 현재값은 사용자가 화면에서 보므로 의미만 — 필요하면 "화면의 그 값" 식으로 안내. |
| `location` | `string` | No | UI 내 위치. 예: `"타임라인 topbar, 날짜 네비게이션 오른쪽"`. 사용자가 위치로 물을 때 매칭 도움. |

**불변식**: `id` unique, `meaning` non-empty. 추가 필드 허용(forward-compatible, BR-6).

**예시**:
```json
{
  "id": "topbar.today_cost",
  "location": "타임라인 topbar, 날짜 네비게이션 오른쪽",
  "meaning": "오늘 에이전트 LLM 턴 비용 합계 (USD). 화면의 $ 값이 그 합계입니다."
}
```

---

## E2: UiLegend (정적 파일)

전체 legend. `UiLegendEntry` 배열.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `entries` | `UiLegendEntry[]` | **Yes** | TUI 요소별 legend 항목 |

**파일 위치**: parent repo 고정 경로(예 `operator-console/src/ui-legend.json`). git 관리, 사람 유지.
**로드 방식**: `handleSteerRead`가 `readFileSync(new URL("./ui-legend.json", import.meta.url))` + try/catch로 런타임 read (top-level `import`은 malformed 시 MCP 서버 spawn crash → 금지, BR-4). codebase verb(steer-handler.ts:113)의 파일-read 선례와 동일.
**메타데이터**(`generated_at`/`tui_version`) 불필요 — 정적이므로 git 이력이 곧 버전.

---

## E3: LegendResponse (MCP 도구 출력)

`steer_read{command:"/ui-legend [element]"}` 의 응답. `handleSteerRead`는 **string** 반환(`mcp-server.ts:69` `content:[{type:"text", text}]`, `/turns`·`/codebase` 패턴과 동일) → legend(또는 필터된 부분집합)를 `JSON.stringify`한 텍스트. element 인자는 parser가 아니라 **handler가 `draft.args.raw`에서 split**해 얻는다(READ_VERBS는 raw만 넘김, parser.ts:77).

```json
// /ui-legend topbar.today_cost
{
  "legend": [
    {
      "id": "topbar.today_cost",
      "location": "타임라인 topbar, 날짜 네비게이션 오른쪽",
      "meaning": "오늘 에이전트 LLM 턴 비용 합계 (USD). 화면의 $ 값이 그 합계입니다."
    }
  ]
}
```

- `element` 인자 → `id` exact match로 필터.
- element 없으면 전체 `entries`.
- element not found → `{"legend":[], "error":"element 'x' not found"}`.
- 현재값 필드 없음 (제외).
