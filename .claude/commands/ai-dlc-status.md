---
description: 현재 AI-DLC 진행 상황 대시보드 — phase/stage, 승인 대기, 스킵 항목, ledger (읽기 전용)
argument-hint: "[선택: unit 이름으로 범위 한정]"
allowed-tools: Read, Glob, Grep, Bash(git status:*), Bash(git diff --stat:*)
---

# /ai-dlc-status — 진행 상황 대시보드 (읽기 전용)

현재 AI-DLC 작업 상태를 한눈에 요약한다. **어떤 파일도 수정하지 않는다.**

범위: $ARGUMENTS (비어 있으면 전체)

## 수집 항목

1. **State.** `aidlc-docs/aidlc-state.md`:
   - 현재 phase(INCEPTION / CONSTRUCTION / OPERATIONS).
   - stage별 완료 `[x]` / 스킵 / 진행 중 목록.
   - `## Extension Configuration`의 enabled/disabled.

2. **다음 액션 & 게이트.** `aidlc-docs/audit.md`의 최근 항목에서:
   - 마지막 완료 단계와 다음에 할 일.
   - **승인 대기** 중인 게이트가 있는지.
   - 미응답 질문 파일이 있는지(`aidlc-docs/inception/**/...questions.md`,
     `**/*-questions.md`에서 비어 있는 `[Answer]:` 태그 탐지).

3. **Plan 진척도.** 진행 중 stage의 plan 체크박스를 세어 `완료/전체` 비율.
   - `aidlc-docs/construction/<unit>/code/...`, `.../plans/...`.

4. **Refactor/Deprecate ledger.** 있으면
   `aidlc-docs/inception/refactor/<name>/2-tier-ledger.md`의 T1/T2/T3 카운트와
   **미해결 T3 항목**(사용자 결정 대기)을 별도로 표시.

5. **작업 트리.** `git status`(요약)와 `git diff --stat`으로 현재 미커밋 변경 규모.

## 출력 형식

```
# AI-DLC Status — <project>

Phase: <…>   |   Stage: <…>   |   Unit: <…>

진행:
  ✅ 완료: <stage 목록>
  ⏳ 진행 중: <stage> (plan N/M)
  ⏭️  스킵: <stage 목록 + 사유>

🚦 대기 중 게이트:
  - <승인 대기 / 미응답 질문 — 없으면 "없음">

🧩 Extensions: <enabled / disabled>

🔧 Refactor/Deprecate ledger (있으면):
  T1 n · T2 n · T3 n  (미해결 T3: <목록>)

📦 작업 트리: <변경 파일 수, +/- 라인>

➡️  다음 액션: <한 줄>
```

해당 아티팩트가 없으면 그 섹션은 "해당 없음"으로 표기하고, `aidlc-state.md`가
아예 없으면 "진행 중인 AI-DLC 작업 없음 — `/ai-dlc-request`로 시작"이라고 안내한다.
