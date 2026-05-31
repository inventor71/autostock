# F7 — Code Generation Part 1 (구체 카피 제안)

> **트랙**: F7 / **단계**: CONSTRUCTION → Code Generation Part 1 / **상태**: 승인 대기 (rev3: 로케일은 placeholder만, 팁은 영어 단일)
> **요구사항**: `inception/requirements/console-trading-native-copy.md` (APPROVED; FR-3.1 슬림 + FR-5 rev2 로케일 범위)
> **대상 포크**: submodule `operator-console/cli` @ `0fa8fc1`

## Step 0 — worktree (Part 2 첫 동작)
- [ ] `git worktree add .claude/worktrees/f7-copy -b feat/console-trading-copy`; 포크 submodule F5 베이스 체크아웃.

## Step 1 — 로케일 헬퍼 (신규, 소형 — placeholder 전용)
- [ ] `home.tsx` 상단 한 줄:
  ```ts
  const KO = (process.env.LC_ALL || process.env.LC_MESSAGES || process.env.LANG ||
    (typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().locale : "") || ""
  ).toLowerCase().startsWith("ko")
  ```

## Step 2 — 홈 placeholder (`routes/home.tsx` L19-21), 한/영 (FR-5)
- [ ] `placeholder.normal`을 `KO` 분기:
  ```ts
  normal: KO
    ? ["애플 절반 팔아", "신규 진입 중지", "지금 포지션 보여줘"]
    : ["sell half my AAPL", "pause new entries", "what are my open positions?"],
  shell: ["ls -la", "git status", "pwd"],   // 실제 셸 입력, 유지
  ```

## Step 3 — `NO_MODELS_TIP` 리브랜드 (`tips-view.tsx` L71), 영어 단일
- [ ] `"Run {highlight}/connect{/highlight} to add an AI provider and start steering your trader"`
  (로케일 분기 없음 — 팁 슬롯은 영어 단일 유지.)

## Step 4 — TIPS: 트레이딩-우선 풀로 재구성 (사용자 결정: "트레이딩 우선 + 유용 일반팁 소수")
`TIPS` 배열을 **[트레이딩 9개 + 유용 일반팁 ~8개]** 로 재정의(나머지 ~90개는 홈 회전에서 제외). 트레이딩 팁 노출 ≈ 50%+.
- **유지하는 일반팁(~8, 콘솔에서 실제 유용)** — 기존 항목 그대로 남김(함수형 팁은 `shortcuts` 의존 유지, `Shortcuts` 타입/객체는 그대로 둠):
  - `@`+파일명 fuzzy 검색·첨부 (차트/CSV 컨텍스트) (L165)
  - 사이드바 토글 — 라이브 트레이딩 사이드바 표시/숨김 (fn, sessionSidebarToggle, L191)
  - `/new` 새 세션 (fn, sessionNew, L177)
  - `/sessions` 세션 목록·핀·이어가기 (fn, sessionList, L178)
  - AI 응답 중단 (fn, sessionInterrupt, L200)
  - 명령 팔레트 — 모든 액션 보기 (fn, commandList, L187)
  - `/models` 모델 전환 (fn, modelList, L175)
  - `/compact` 긴 세션 요약 (L184)
  - `/help` 도움말 (fn, helpShow, L281)
- **제외(홈 회전에서 빼기)**: 코딩 전용 14개(`/init`, `opencode run`/`run -f`/`serve`/`run --attach`/`agent create`,
  github 4종, `docker run`, `AGENTS.md`, `/review`) + 딥한 opencode-dev/config 팁(`.opencode/{commands,agents,tools,plugins,
  themes}`, `opencode.json`/`tui.json` 상세, permission 패턴, `{env:}`/`{file:}`, `/share`, `/undo`·`/redo`, Plan/Build·
  `@agent-name`, 페이지 탐색/핀/quick-switch/timeline/conceal/scroll/username/rename/leader/editor/paste/`/themes`/`/status`/
  `/connect` 등). (실경로/실설정은 코드·문서에 그대로 존재 — 단지 홈 *팁 회전*에서만 제외.)

## Step 5 — TIPS: 트레이딩 팁 9개 (capability 위주, 영어 단일)
- [ ] 아래 영어 팁을 TIPS 앞쪽에 둠 (로케일 분기 없음 — FR-5 rev2).

```ts
// --- autostock steering tips (F7) ---
"Just talk to it — say {highlight}sell half my AAPL{/highlight} and the agent proposes the order",
"Ask about your book anytime — {highlight}show my positions{/highlight}, {highlight}what's my P&L?{/highlight}",
"Stop fast when you need to — {highlight}flatten everything{/highlight}, {highlight}pause new entries{/highlight}, or {highlight}kill{/highlight}",
"If the agent tries to trade a symbol you touched, it waits — say {highlight}approve{/highlight} or {highlight}reject{/highlight}",
"Every order is confirmed before it runs — this console only steers the trader, nothing else",
"Set stops and trades in words — {highlight}stop AAPL at 180{/highlight}, {highlight}buy NVDA $5000{/highlight}, {highlight}sell TSLA 50%{/highlight}",
"Point the agent without trading — {highlight}no tech buys today{/highlight}",
"See the reasoning — {highlight}why did you buy NVDA?{/highlight}, {highlight}show recent decisions{/highlight}",
"Break glass anytime in the Alpaca dashboard — the agent reconciles to match",
```

## Step 6 — 검증 (Part 2)
- [ ] `tsgo --noEmit` 클린 (`Tip`/markup 계약 보존, `KO` 분기 타입 OK).
- [ ] launcher(26) + console-own 테스트 그린(무회귀, AC-5); `LANG=ko_KR.UTF-8` vs 영문 로케일 placeholder 스모크.
- [ ] diff = 카피 + 로케일 헬퍼에 한정(AC-6); 가공 명령 0건(AC-4); MCP 모델 정확(AC-7).
- [ ] 커밋(포크 submodule); 부모 re-pin/push/merge = **사용자 승인 후**(outward).

## 비고
- (선택·저우선) FR-4 `debug` `opencode version:` — 백로그.
- 검증은 F5 패턴(bun install + tsgo)으로 worktree/포크 환경에서 수행.
