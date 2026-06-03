# Business Rules — ui-legend

> Track: F28 · Unit: `ui-legend` · Depth: Minimal
>
> **범위 단순화 (사용자 2026-06-02):** 정적 의미 사전만. data_source/현재값/fallback/atomic write 규칙 제거.

## BR-0: verb 등록 — READ_VERBS만, schema.ts 미변경 (critic 2차)

- `ui-legend`를 `parser.ts`의 `READ_VERBS` Set에 추가(parser.ts:21-29의 `codebase` 선례). 끝.
- **`schema.ts`의 `SteeringVerb`/`ALL_VERBS`/golden contract는 건드리지 않는다** — READ_VERBS 멤버(`status`/`turns`/`codebase`/`agent-trace`)는 `SteeringVerb`에 없고 parser.ts:77에서 `as SteeringVerb`로 캐스팅되는 **콘솔 전용 read pseudo-verb**(파일-드롭 안 됨, 데몬 미관여). schema.ts에 추가하면 오히려 cross-language golden contract test(`contract.test.ts` vs `records.py`)를 깨뜨림.
- 하이픈 `ui-legend`는 `agent-trace` 선례로 안전(READ_VERBS는 하이픈 토큰 허용; parseCommand는 whitespace로만 split, parser.ts:64).

## BR-1: id 필수 · Unique

- `id`는 **필수**, non-empty. legend 내 **unique**. 중복 시 리뷰에서 검출(또는 첫 항목만 유지).
- 권장 형식: dot-hierarchy (`"영역.요소"`). 의미 기반 id 권장(위치 기반보다 UI 변경에 강건).

## BR-2: meaning 필수 · Non-empty

- `meaning`은 **필수**, non-empty, 한국어(프로젝트 기본 언어).
- 에이전트가 그대로 표시할 설명문. 완전한 문장 권장. 현재값은 안 줌 → "화면의 그 값"으로 안내하는 표현 권장.
  - 좋은 예: `"오늘 에이전트 LLM 턴 비용 합계 (USD). 화면의 $ 값이 그 합계입니다."`

## BR-3: element 필터 — Exact match (handler에서 추출)

- element 인자는 **`handleSteerRead`가 `draft.args.raw`에서 추출**한다 — parser의 READ_VERBS 분기는 `args:{raw:trimmed}`만 넘기고 element를 split하지 않음(parser.ts:77). raw를 whitespace로 split → head(`ui-legend`) 제거 → 나머지가 element.
- `id`와 **정확히 일치**하는 항목만. substring/regex 없음.
- 일치 없으면 `{"legend":[], "error":"element '<x>' not found"}`.
- element 없으면(`/ui-legend`) 전체 entries.

## BR-4: 서빙 resilience

- `ui-legend.json` 로드는 **`readFileSync` + try/catch**(top-level `import` 금지). codebase 선례(steer-handler.ts:113-114)처럼 파일 누락/parse 실패 시 빈 legend 또는 안내 메시지 반환 → **MCP 서버 crash 금지**.
  - ⚠️ top-level `import x from "./ui-legend.json"`은 `src/`에 빌드 단계가 없어(`bun run mcp-server.ts` 직접 실행) malformed JSON이 **서버 spawn 시 crash** → `autostock_steer` 미등록 → 에이전트가 "주문 못 한다"고 답하는 광범위 실패. 그래서 import 금지, runtime read.
- verb 파싱은 기존 `parseCommand` 경로 재사용 — 잘못된 입력은 기존 `rejected: ...` 패턴.

## BR-5: Drift 관리 (규약)

- UI(F25/F6 등)를 바꾸는 PR에서 `ui-legend.json`도 함께 업데이트 — 리뷰어가 확인.
- 자동생성 메커니즘 없음(의미는 UI 텍스트보다 안정적이라 정적 유지로 충분 — 사용자 판단).
- 의미가 오래되어도 안전 실패(틀린 값이 아니라 약간 낡은 설명) — 매매·권한에 영향 0.

## BR-6: 확장성 (Forward Compatibility)

- 스키마는 추가 필드에 **열려 있음**(additional properties 허용). Unknown 필드 무시.
- 향후 `aliases`(검색 키워드), `examples`, `see_also` 등 추가 가능. `id`/`meaning`만 필수.
- 새 UI 요소 = JSON 항목 하나 추가. 코드 변경 불필요.
