---
description: AI-DLC 작업을 aidlc-state.md 기준 중단점부터 재개
argument-hint: "[선택: 특정 unit/stage 이름 — 비우면 state가 가리키는 다음 단계]"
---

# /ai-dlc-resume — 중단점부터 재개

이전 세션에서 진행하던 AI-DLC 작업을 **상태 파일 기준으로 이어서** 진행한다.

재개 대상: $ARGUMENTS
(비어 있으면 — 트랙 인자가 있으면 그 트랙, 없으면 Registry의 유일한 `active` 트랙. active가
여러 개면 어느 트랙을 재개할지 먼저 묻는다.)

## 진행 절차

1. **세션 연속성 규칙 로드.** 룰셋 디렉터리(`.aidlc-rule-details/`)에서
   `common/session-continuity.md`, `common/process-overview.md`, `common/concurrent-tracks.md`를 로드.

2. **트랙 선택 + 상태 파악.** 다음을 읽고 현재 위치를 재구성한다:
   - 루트 `aidlc-docs/aidlc-state.md`의 **Track Registry** — 재개할 트랙(`<id>`)·브랜치·worktree 확인.
   - **그 트랙의** `aidlc-docs/tracks/<id>/state.md` — 완료/스킵/진행 중 stage, Extension Configuration.
   - **그 트랙의** `aidlc-docs/tracks/<id>/audit.md`의 **최근 항목** — 마지막 사용자 입력·승인·다음 액션.
     (루트 `audit.md`는 머지 요약용이므로 진행 맥락은 트랙 audit에서 본다.)
   - 진행 중 stage의 plan 파일 체크박스(`aidlc-docs/construction/<unit>/...`,
     `aidlc-docs/inception/.../plans/...`) — 어느 step까지 [x]인지.
   - **worktree 확인**: `git worktree list`로 그 트랙 worktree에 있는지. 코딩 단계인데 worktree가
     없으면 먼저 생성하라고 안내(코드는 worktree 안에서만).
   - `/ai-dlc-refactor` 작업이면 `aidlc-docs/inception/refactor/<name>/2-tier-ledger.md`의
     정지 지점(특히 미해결 T3 항목).

3. **재개 지점 요약 제시.** 사용자에게 2~4줄로:
   - 지금 어느 phase/stage/unit에 있는지,
   - 마지막으로 완료한 것과 **바로 다음에 할 일**,
   - 사용자 입력 대기 중인 게이트(미응답 질문·미승인 단계)가 있으면 명시.

4. **게이트 확인.** 다음 단계가 **승인 대기**거나 **미응답 질문**이면, 자동 진행하지 말고
   해당 질문/승인을 다시 제시하고 멈춘다. 그 외에는 CLAUDE.md 워크플로대로 이어서 진행한다.

5. **기록.** 이 재개 호출과 사용자 응답을 **그 트랙의** `aidlc-docs/tracks/<id>/audit.md`에 append.

## 주의

- 상태가 모순되거나(예: state는 완료인데 plan 체크박스는 미완) 애매하면 **추측하지 말고**
  무엇을 다음으로 할지 사용자에게 확인한다.
- Registry에 `active` 트랙이 없으면 재개할 작업이 없는 것 — `/ai-dlc-request`로 새로 시작하라고 안내.
