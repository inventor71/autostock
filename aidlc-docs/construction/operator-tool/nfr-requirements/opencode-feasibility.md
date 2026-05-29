# Unit B (`operator-tool`) — opencode 능력 사전 조사 (PreToolUse/권한 방식 충분성)

_AI-DLC 트랙 F4 · Unit B · NFR Requirements 사전 조사 · 2026-05-29._
_계기: FD 승인 게이트에서 사용자 질문 — "PreToolUse 방식을 진행하기에 opencode fork가 충분한지 조사해야 하지 않나?"_

> **구분(중요):** BR-10.1의 PreToolUse 훅은 **에이전트(claude) 세션**을 가두는 Claude Code 기능이다(opencode 아님).
> opencode는 **운영자 도구(Unit B)**, 즉 *고권한* 측이며, 가두는 게 아니라 *자기 LLM의 도구 표면을 제한*해야 하는 쪽이다.
> 따라서 두 조사가 분리된다: (A) 에이전트측 = Claude Code 헤드리스 훅, (B) 운영자측 = opencode 능력/한계.

## A. 에이전트측 (Claude Code, `claude -p` 헤드리스) — BR-10.1
- PreToolUse 훅은 settings.json에 구성되며 **권한모드와 무관하게 실행되어 deny 반환 가능**(`--permission-mode dontAsk`여도
  훅의 hard-deny는 유효). 에이전트 cwd=`workspace/`이므로 훅 구성 파일 위치(프로젝트/유저/`workspace/.claude/`)와
  `-p` 모드 적용을 **코드젠에서 실측 검증**(verification item). 결론: BR-10.1는 Claude Code 측에서 실현 가능, opencode 무관.

## B. 운영자측 (opencode fork) — 충분성 판정: **충분(조건부)**

### 가능 (Unit B 요구 충족)
- **권한 시스템**(`allow`/`ask`/`deny`, 와일드카드, **에이전트별 오버라이드**, bash 명령 패턴, `external_directory`(기본 ask),
  `.env` 읽기 기본 차단). → 운영자 에이전트를 **file-drop 커스텀 툴 1개만 allow, bash/edit/webfetch/`task`/external_directory
  deny**로 잠글 수 있음.
- **플러그인 훅**(`tool.execute.before/after` 차단·수정, **커스텀 툴**=Zod 스키마+결정적 execute, `shell.env` env 주입,
  `command.executed`/`permission.asked` 이벤트). → 매매를 **결정적 커스텀 툴**로 구현(토큰 부착+원자적 append를 코드가 수행).

### ⚠ 알려진 보안 버그 (방어 설계 필수)
- **#5894:** `tool.execute.before`가 **서브에이전트(task) 툴 호출 미가로챔 → 정책 우회**. → 운영자 에이전트 **`task` deny**.
- **#7006 / #19927:** `permission.ask` 플러그인 훅 **미트리거/우회**. → confirm을 `permission.ask`에 **의존 금지**.
- **#6396:** **SDK 구동 시 에이전트 `deny` 권한 무시**. → opencode를 SDK/헤드리스로 몰면 deny가 안 먹을 수 있음 → fork에서 검증.

### 핵심 — confirm 무결성 (사용자 직감 적중)
운영자측은 **LLM**이라 "LLM이 묻고→사람 y→LLM이 `confirmed=True` 기록" 구조면 **injection된 LLM이 confirm을 위조** 가능.
데몬은 `confirmed`+토큰만 보므로 통과된다. → **사람 확인은 LLM이 만질 수 없는 결정적 레이어가 잡아야 한다:**
**커스텀 툴의 `execute` 함수(결정적 코드)가 자체 사람-확인 + 토큰 부착 + 원자적 append를 수행**하고, LLM은 그 툴을
*호출*만 한다(args 제안). + `task` deny로 #5894 차단.

### 결론
opencode fork는 충분하다 — 단 **(1) 매매=결정적 커스텀 툴(execute가 confirm·토큰·append 소유), (2) 권한 잠금
(bash/edit/webfetch/task/external_directory deny), (3) confirm은 permission.ask에 의존 금지, (4) SDK deny 동작을
fork에서 검증** 을 전제로. 그리고 **최종 안전 경계는 데몬측(Unit A: confirmed+토큰+RiskManager 게이트)** 이며
opencode 잠금은 defense-in-depth(단독 게이트 아님).

## 출처
- opencode Permissions: https://opencode.ai/docs/permissions/
- opencode Plugins: https://opencode.ai/docs/plugins/
- opencode Agents/Config: https://opencode.ai/docs/agents/ , https://opencode.ai/docs/config/
- Issue #5894 (tool.execute.before subagent bypass), #7006/#19927 (permission.ask 미트리거), #6396 (SDK deny 무시).
