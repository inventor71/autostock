# F4 Unit B (operator-console) — Code Generation Plan

**Unit**: operator-console (opencode hard-fork)
**Stage**: CONSTRUCTION → Code Generation (Part 2, 재개)
**설계 상태**: 승인됨 (F4 Q1–Q9 + Clarif-1/2, 메모리 `steering-console-redesign.md`)
**범위(이번 픽업)**: Phase 2 잔여 + Phase 3. Phase 4(컨트랙트/e2e)는 이후.
**작업 위치**: 서브모듈 `operator-console/cli`(opencode 포크) + `operator-console/src`(공유 결정론 코어)

## 불변 안전 계약 (모든 단계에서 유지)
- 콘솔(LLM 포함)은 **주문 권한 없음**. 제안만 하고, 사람이 confirm, 데몬의 `RiskManager→Broker` 게이트가 실제 경계.
- 데몬과의 유일한 통신 = repo-root `steering/` 파일드롭 채널(commands/events/snapshot) — Unit A 소유 계약.
- 🚫 opencode에서 Claude 구독 사용 금지(ToS). 콘솔 LLM = 비-Anthropic(OpenAI OAuth).
- 변경마다 검증: `bun test`(operator-console) + `tsgo` 타입체크 + `bun run verify-lockdown.ts`.

---

## Phase 2 — TUI 패널 + LLM-bypass 경로

### Step 1: 사이드바 패널 확장 — open-orders + event-feed ✅ (2026-05-30)
- [x] `feature-plugins/sidebar/autostock.tsx`: snapshot의 `open_orders`를 표시(심볼/stop/limit).
- [x] `steering/events.jsonl` tail 기반 event-feed(최근 5개) 추가 — torn-line 안전 읽기, 폴링 1.5s.
- [x] 읽기 전용 유지(데몬 round-trip 없음). `tsgo` 타입체크 통과(0 errors).

### Step 2: ~~순수 키스트로크 LLM-bypass 명령 경로~~ — **REMOVED (NL-only 결정, 2026-05-30)**
**결정:** 구현·라이브 검증(팔레트 노출)까지 마친 뒤, 사용자와 원론 논의 끝에 **NL-only로 단순화**하기로 하고
키스트로크 경로를 **제거**함. 근거: 두 경로가 같은 confirm + `RiskManager→Broker` 게이트를 공유해 안전성은
동일하고, 두 번째 경로의 값은 "타이핑 절약"뿐 → 깔끔함 우선. 결정성은 MCP 경로 내부의 `parser.ts`(검증기)에
그대로 유지. 트레이드오프 수용: steering이 콘솔 LLM(OpenAI) 가용성에 의존, LLM/API 다운 시 break-glass=Alpaca UI(이후 reconcile).
**제거 파일:** `src/tui-plugin.ts`, `src/dispatch.ts`, `src/console-stub.ts`, `test/tui-plugin.test.ts`,
`test/dispatch.test.ts`, `test/e2e/`(PTY injection). **복구:** `.opencode/tui.json` autostock-steer 엔트리 제거,
`opencode.json` 서버-plugin 엔트리 제거. **유지(MCP/NL 경로 + 코어):** `mcp-server.ts`/`steer-handler.ts`/
`parser.ts`/`filedrop.ts`/`schema.ts` + 테스트(parser/filedrop/steer-handler 19 그린).

<details><summary>(참고) 제거 전 구현 내용</summary>
**설계 결정(조사 완료 2026-05-30):** 결정론 코어를 `cli` 서브모듈에 복제하지 않는다(경계 보존). 대신
`operator-console/src`에 **외부 TuiPlugin**(`tui-plugin.ts`)을 만들어 `@opencode-ai/plugin/tui`로 슬래시 명령
`/steer`를 등록하고, 입력을 `dispatch.ts`의 `Dispatcher`로 라우팅한다. opencode는 이를 외부 플러그인으로 로드
(MCP 서버를 외부 프로세스로 띄우는 것과 같은 경계). 다이얼로그는 JSX 구문 없이 `api.ui.DialogPrompt(...)`/
`DialogConfirm(...)` 컴포넌트 함수 **호출**로 구성(빌드용 solid JSX 설정 회피). `await_confirm` →
비파괴는 DialogConfirm(y/N), 파괴는 DialogPrompt에서 정확히 `CONFIRM` 요구. 토스트는 `DispatchOutcome` 기준.
- [x] `operator-console/src/tui-plugin.ts` — 외부 TuiPlugin(`export default {id,tui}`), `keymap.registerLayer`로
      `autostock.steer` 팔레트 명령 등록, `run()`(LLM 비경유) → DialogPrompt → `Dispatcher` 재사용.
      다이얼로그는 JSX 없이 `api.ui.DialogPrompt/DialogConfirm` 함수 호출. await_confirm: 비파괴=DialogConfirm(y/N),
      파괴=DialogPrompt(literal CONFIRM). 토큰 부재 fail-closed.
- [x] confirm/취소(no-op)/에러 리셋이 `dispatch.ts` 계약과 일치(같은 Dispatcher 인스턴스를 두 다이얼로그가 공유).
- [x] 콘솔 config에 plugin 로드: **`cli/.opencode/tui.json`의 `plugin` 배열**에 `["../../src/tui-plugin.ts",{enabled,label,keybinds:{"autostock.steer":"<leader>s"}}]`.
      **주의(라이브 디버그로 발견):** `opencode.json`의 `plugin`은 **서버 플러그인**(`server()` 필요)이라 tui-only 플러그인을
      거기 넣으면 "must default export server()" 에러로 거부됨. 외부 TUI 플러그인은 TUI config(`tui.json`)의 `plugin`(= `plugin_origins`)으로 등록해야 함.
- [x] 단위 테스트 `test/tui-plugin.test.ts` 7개 그린(읽기 무기록/거래 confirm/파괴 CONFIRM/취소 no-op/토큰부재/파스에러) + tsc(src) 0 errors.
- **미지수(라이브 검증 필요):** 외부 .ts tui-plugin 실제 로딩(file:// + zod 해석) + 다이얼로그 컴포넌트 직접 호출 렌더링 + 팔레트 노출. 헤드리스로는 안전 로직만 커버됨 → `bun dev`에서 확인.
</details>

---

## Phase 3 — side-effect 툴 컴파일타임 제거 (보안 하드닝, NFR-1)

### Step 3: registry.ts 락다운 필터 ✅ (2026-05-30)
- [x] `registry.ts` `builtin`에서 side-effect 툴(bash/edit/write/task/fetch/search/patch/repo_*)을
      락다운 시 제외 → LLM 레지스트리에 미등록. 유지: read/glob/grep/lsp + invalid(폴백) + custom(MCP steer).
- [x] **결정 변경:** 기본 ON이 아니라 **opt-in `AUTOSTOCK_LOCKDOWN=on`** — 기본 ON은 상속한 opencode
      테스트 2개(scout repo-tools / task background-param)를 깨고 upstream 재핀 마찰↑. permission default-deny가
      항상 켜져 있어(layer 1) opt-in이어도 방어는 유지. 플래그는 layer-build 시점에 읽어 테스트별 토글 가능.
- [x] 콘솔 런치(`bun dev`)가 `AUTOSTOCK_LOCKDOWN=on`을 기본 세팅(커밋된 `cli/package.json` dev 스크립트)
      → gitignore된 `.env` 의존 없이 콘솔은 항상 락다운.

### Step 4: 검증 강화 — 부재(absence) 단언 ✅ (2026-05-30)
- [x] **2-레이어 검증.** layer1(permission): `verify-lockdown.ts` PASS(deny/allow/ask, real engine).
      layer2(compile-time 부재): `test/tool/registry.test.ts`에 id-agnostic 단언 추가 — 락다운 시 살아남은
      모든 builtin이 read-only allowlist 안에 있음(어떤 side-effect 툴도 못 빠져나감) + bash/edit/write/task/
      webfetch/websearch/apply_patch 부재 + 기본(미설정)엔 full 유지. registry 테스트 16개 그린.
- [x] `verify-lockdown.ts` 헤더를 2-레이어로 갱신(부재는 registry 테스트가 권위).

### Step 5: baseline 핀 + 리브랜딩 문서화 ✅ (2026-05-30)
- [x] upstream `sst/opencode` **v1.15.12**(초기 스파이크 커밋 `0147908`)로 핀 — README "Pinned baseline".
- [x] 브랜딩은 표면만(재핀 비용 최소화) 방침 문서화. README 로드맵 Phase 3 → done.

---

## Phase 4 — 크로스랭귀지 컨트랙트 테스트 ✅ (2026-05-30)
NL-only라 콘솔↔데몬 파일드롭 JSON이 유일 결합점 → verb/event-kind/envelope-필드 드리프트 가드.
- [x] 골든 `operator-console/contract/contract.json` — Unit A pydantic introspection(`get_args`+`model_fields`)으로 생성.
- [x] Python `tests/test_steering_contract.py` — live 모델 == 골든 + TS-shape 명령/이벤트 validate + round-trip (4 그린). standalone `--write` 재생성(`sys.path` 부트스트랩).
- [x] TS `operator-console/test/contract.test.ts` — `schema.ts` 런타임 상수(ALL_VERBS/ALL_EVENT_KINDS/COMMAND_FIELDS/EVENT_FIELDS) == 골든 + `FileDrop.build` envelope == 골든 (5 그린).
- [x] `schema.ts` 망라성 타입체크(`satisfies` + `Exclude<…> extends never`) — 타입↔런타임 양방향 핀, tsc 0 errors.
- [x] **음성 검증**: 골든에 가짜 verb 주입 → Python·TS 둘 다 FAIL 확인 후 복구(가드에 이빨 있음 증명).
- 스코프 노트: per-verb args 시맨틱(commands.py 핸들러)은 별도(parser.test + 데몬 명령 테스트). 이번은 envelope+enum 스키마 계약.

## Build & Test (마무리)
- [ ] `operator-console`: `bun test` 그린 + `tsgo` 타입체크 클린.
- [ ] `bun run verify-lockdown.ts` 통과(allow/deny/ask + 부재 단언).
- [ ] Python 회귀: `pytest -q` 273 그린(콘솔 변경이 Unit A에 영향 없음 확인).
- [ ] 서브모듈 핀 업데이트 + 부모 repo에서 포인터 커밋. 머신-로컬 `.opencode/opencode.jsonc`는 커밋 제외.

## 추적성
- Phase 2 ↔ F4 Q4(NL 제안+confirm)/Q5(에이전트 read+event-feed) / Phase 3 ↔ F4 Q8(NFR-1 권한 구조적 분리, SECURITY-11).
