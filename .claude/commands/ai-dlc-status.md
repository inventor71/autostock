---
description: 현재 AI-DLC 진행 상황 대시보드 — phase/stage, 승인 대기, 스킵 항목, ledger (읽기 전용)
argument-hint: "[선택: 트랙 ID(F9 등)로 범위 한정 — 비우면 모든 active 트랙]"
allowed-tools: Read, Glob, Grep, Bash(git status:*), Bash(git diff --stat:*), Bash(git worktree list:*)
---

# /ai-dlc-status — 진행 상황 대시보드 (읽기 전용)

현재 AI-DLC 작업 상태를 한눈에 요약한다. **어떤 파일도 수정하지 않는다.**

범위: $ARGUMENTS (비어 있으면 모든 `active` 트랙)

## 수집 항목

0. **Track Registry.** 루트 `aidlc-docs/aidlc-state.md`의 `## Track Registry` 테이블에서
   트랙 목록(id/title/status/branch/worktree)을 읽는다. 범위 인자가 있으면 그 트랙만,
   없으면 모든 `active` 트랙을 대상으로 아래를 트랙별로 수집한다.

1. **트랙 State.** **각 트랙의** `aidlc-docs/tracks/<id>/state.md`:
   - 현재 phase(INCEPTION / CONSTRUCTION / OPERATIONS).
   - stage별 완료 `[x]` / 스킵 / 진행 중 목록.
   - Extension Configuration의 enabled/disabled.

2. **다음 액션 & 게이트.** **각 트랙의** `aidlc-docs/tracks/<id>/audit.md` 최근 항목에서:
   - 마지막 완료 단계와 다음에 할 일.
   - **승인 대기** 중인 게이트가 있는지.
   - 미응답 질문 파일이 있는지(`aidlc-docs/inception/**/...questions.md`,
     `**/*-questions.md`에서 비어 있는 `[Answer]:` 태그 탐지).

3. **Plan 진척도.** 진행 중 stage의 plan 체크박스를 세어 `완료/전체` 비율.
   - `aidlc-docs/construction/<unit>/code/...`, `.../plans/...`.

4. **Refactor/Deprecate ledger.** 있으면
   `aidlc-docs/inception/refactor/<name>/2-tier-ledger.md`의 T1/T2/T3 카운트와
   **미해결 T3 항목**(사용자 결정 대기)을 별도로 표시.

5. **작업 트리 & worktree 위반.** `git worktree list`로 트랙별 worktree 존재 확인,
   `git status`(요약)·`git diff --stat`으로 미커밋 변경 규모. **위반 감지**:
   - `main` 작업 트리에 미커밋 **코드** 변경이 있으면(worktree 게이트 위반) ⚠️ 표시.
   - 서브모듈(`operator-console/cli`)이 detached HEAD인데 변경이 있으면 ⚠️ 표시.

## 출력 형식

```
# AI-DLC Status — <project>

Tracks (registry): <id:status …>
⚠️ worktree 위반: <main에 미커밋 코드 / submodule detached — 없으면 생략>

── <id> · <title> ── [<branch> @ <worktree>]
Phase: <…>   |   Stage: <…>   |   Unit: <…>
진행:
  ✅ 완료: <stage 목록>
  ⏳ 진행 중: <stage> (plan N/M)
  ⏭️  스킵: <stage 목록 + 사유>
🚦 대기 중 게이트: <승인 대기 / 미응답 질문 — 없으면 "없음">
🧩 Extensions: <enabled / disabled>
🔧 Refactor/Deprecate ledger (있으면): T1 n · T2 n · T3 n  (미해결 T3: <목록>)
➡️  다음 액션: <한 줄>

── <다음 active 트랙> ──
…

📦 작업 트리(전체): <변경 파일 수, +/- 라인>
```

- 각 `active` 트랙마다 한 블록씩 출력(범위 인자가 있으면 그 트랙만).
- 해당 아티팩트가 없으면 그 줄은 "해당 없음"으로 표기.
- Registry에 `active` 트랙이 없으면 "진행 중인 AI-DLC 작업 없음 — `/ai-dlc-request`로 시작"이라고 안내.
