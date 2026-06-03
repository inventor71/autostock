# Code Generation 계획 (Part 1) — Unit B `operator-tool` (F4, opencode 하드 fork)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit B · Code Generation · 2026-05-30._
_입력: Unit B FD(BR-B*) + NFR Design(P-B1..8) + tech-stack(sst/opencode, MIT, **TS/Bun + OpenTUI**; Go 아님 — S0 정정)._
_원칙: **스파이크 우선 → go/no-go → 수직 슬라이스 → 전체**. Unit A 계약(file-drop+토큰)은 불변._

## 위치/격리
- opencode fork는 **별도 코드베이스**(TS/Bun)다. Python 레포를 더럽히지 않게 **별도 디렉토리/레포로 소유**
  (예: 사이드 레포 `autostock-console`, 또는 이 레포 내 `operator-console/` 서브트리 — **스파이크에서 확정**).
- Unit A처럼 새 브랜치/worktree에서 작업; 라이브 무영향.

---

## Phase 0 — fork-feasibility 스파이크 (Code Gen 진입 1순위, NFR-Req §6)
**목적:** 최대 미지수를 제거하고 P-B2/P-B3 구현 형태와 파일 경로를 확정. 각 항목 go/no-go.

- [x] **S0.1 레포/라이선스** ✅(정적) — `sst/opencode`, **MIT**, baseline HEAD `16cae9a`. **순수 TS/Bun(Go 0)**. — 정식 레포·태그 확정(`sst/opencode` vs 리네임 이력), **MIT 라이선스 파일/고지 확인**, baseline commit 핀.
- [~] **S0.2 빌드/실행** — `bun install`이 deps는 받았으나 **네이티브 모듈(tree-sitter/node-pty) 빌드에 `make`/gcc 필요** → 이 샌드박스엔 build-essential 부재(sudo 필요). **추가 정정: 툴체인 = Bun + build-essential(make/gcc/python3)**. 사용자: `sudo apt install -y build-essential python3` 후 `bun install && bun dev`(TUI from source).
- [x] **S0.3 custom tool** ✅(정적) — `packages/plugin` `Plugin`+`tool.execute.before`+`ToolDefinition`(custom tool 등록 가능). — plugin custom tool(`steer`) 등록 + **결정적 `execute`** 동작(인자 받기·파일쓰기) 확인.
- [x] **S0.4 도구 레지스트리** ✅(정적) — `packages/opencode/src/tool/registry.ts` 단일 지점(task/shell/edit/write/webfetch import 제거). — `task`/bash/edit/write/webfetch **컴파일타임 제거 지점** 식별(P-B3).
- [~] **S0.5 커스텀 pane** ✅(정적, 라이브 PoC는 사용자) — `TuiPluginApi`(tui.ts:581): `render`(JSX 패널)·`replace`(모달)·`toast`(알림). OpenTUI=JSX. — Go/Bubble Tea로 **패널 1개 PoC**(예: 정적 텍스트 pane 추가) 성공.
- [x] **S0.6 P-B2 결정** ✅(정적) — in-process TS(클라/서버 분리 아님) → TuiPlugin이 입력 인터셉트→confirm→write 소유. LLM tool은 제안만. **P-B2 기본안 채택(폴백 불필요)**. — LLM tool 결과를 **client가 confirm 후 실행하는 "제안-only"** 가능 여부.
      → 가능: P-B2 기본(Go writer 소유) / 불가: 폴백(TS `steer` execute가 confirm 소유). **여기서 확정.**
- [~] **S0.7 file-drop I/O** — TS `fs`로 자명(빌드 후 사용자 1줄 왕복 확인). — TS/Go에서 repo-root `steering/`에 append/tail/read 동작 + Unit A와 1줄 왕복 확인.
- [~] **S0.8 OpenAI OAuth** — auth에 generic `Oauth` 스키마 존재; **사용자가 `opencode auth login`으로 OpenAI OAuth 라이브 확인**. — opencode `auth login`으로 **비-Anthropic 모델(OpenAI GPT-5.5 류) OAuth** 연결 확인.
      **🚫 하드 제약: Claude 구독(OAuth) 우회 절대 금지** — ToS 위반·계정 밴 시 트레이딩 agent까지 사망. agent=Claude 구독,
      콘솔=OpenAI OAuth 분리. (NL 미작동/불가해도 결정적 경로는 무관 — Phase 1은 LLM 없이도 성립.)
- **게이트:** S0 결과 요약 → 막힌 항목 있으면 NFR Design으로 되돌려 조정. 통과 시 Phase 1.

### Phase 0 정적 분석 결과 (2026-05-30) — 설계 정정
- **Go 불필요**(opencode 현행 = 순수 TS/Bun + OpenTUI). NFR Design의 Bubble Tea/goroutine 가정 폐기 → **OpenTUI(JSX) + TS async**.
- **fork가 더 가벼움**: 패널/모달/토스트 = **TuiPlugin API**(JSX), 도구 제거 = **registry.ts** 1곳, + 리브랜딩/번들 = 우리 plugin. 깊은 코어 수술 없이 'thin fork'.
- 사용자 잔여(Bun만 설치): S0.2 빌드/실행 · S0.5 라이브 pane PoC · S0.7 file-drop 왕복 · S0.8 OpenAI OAuth.

---

## Phase 1 — 수직 슬라이스 (1 명령 end-to-end)
**목적:** 전체 루프를 실코드로 증명(가장 단순 명령 + 1 읽기 패널 + 토큰 게이트).
- [ ] `steering-schema.ts` — E7/E8/snapshot 타입 미러(권위=Unit A).
- [ ] `filedrop/writer`(TS) — 토큰(env) 부착 + `commands.jsonl` 원자 append.
- [ ] `command/parser` + `command/confirm` — `/pause` 결정적 파싱 → ConfirmModal `[y/N]` → write.
- [ ] `filedrop/tail` — events.jsonl tail → outcome(corr_id) 표시(OutcomeWaiter).
- [ ] `panels/statusbar` + 최소 `panels/positions` — snapshot.json read.
- [ ] 토큰 부재 시 쓰기 비활성·상태바 경고(BR-B2).
- [ ] **통합 데모**: 콘솔 `/pause` → commands.jsonl → 로컬 데몬(또는 시뮬 steering/ dir) → events outcome 표시.

---

## Phase 2 — 명령 세트 + 패널 (Q6=A–E)
- [ ] 매매: buy(human-buy 환원 $/sh)/sell(%/sh/$)/flatten/flatten_all/stop — 결정적 파서 + ConfirmModal(파괴적=CONFIRM) + write.
- [ ] 라이프사이클: pause/resume/halt_entries/allow_entries/kill.
- [ ] 승인: pending/approve/reject/unlock(스냅샷·이벤트 기반).
- [ ] 컨텍스트/양방향: note/directive/answer + QuestionInbox(agent_question 이벤트).
- [ ] 패널: positions/orders/P&L · eventfeed(+push 토스트) · pending · questions.
- [ ] **NL 경로**: LLM → CommandDraft 제안 → 동일 ConfirmModal → Go writer(또는 폴백). LLM 쓰기 권한 0.

---

## Phase 3 — 보안 봉쇄 + 리브랜딩 (BR-B4)
- [ ] **컴파일타임 도구 제거**: task/bash/edit/write/webfetch 미등록. side-effect=`steer`+읽기만.
- [ ] **검증 테스트**: 등록 도구 집합 == 허용목록(제거 대상 부재) 단언.
- [ ] 리브랜딩: 바이너리 `autostock-console`/스플래시/시스템프롬프트; 모델·auth 핀.

---

## Phase 4 — 테스트·계약·통합
- [ ] TS 단위: parser/confirm/writer(토큰 부착·원자 append).
- [ ] TS 단위: 스키마 round-trip(+ 폴백 시 steer execute).
- [ ] **cross-language 계약 테스트**: `steering/contract-samples/` 골든을 Unit A(pydantic)·Unit B(TS) 양측 파싱·생산 일치.
- [ ] 통합: 콘솔 ↔ 로컬 데몬/시뮬 — 매매/승인/이벤트 왕복.
- [ ] 의존성 lockfile 핀(SECURITY-10) + MIT 고지.

---

## 산출물 / 완료 기준
- 콘솔(`autostock-console`)이 **결정적 매매·제어·조회 + NL 보조**로 라이브 데몬을 안전하게 운전; LLM은 주문 권한 0;
  side-effect 도구는 컴파일타임에 `steer`로 한정; 계약 테스트 green.
- 문서 요약: `construction/operator-tool/code/code-summary.md`(Part 2 종료 시).
- 이후 **Build & Test 스테이지**(전 유닛 통합) + F3 rebase.

## 리스크
- **High–Medium**(신규 TS/Bun 베이스 소유, 스파이크 의존). 완화: 스파이크 게이트, 수직 슬라이스 우선, 계약 테스트로 스키마
  드리프트 차단, 데몬측 Unit A가 최종 안전. 콘솔은 별 프로세스라 Python 회귀 위험 0.
