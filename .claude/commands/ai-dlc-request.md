---
description: 새 개발 요청을 AI-DLC 적응형 워크플로로 시작 — 의도 분석부터 단계별 승인 게이트까지
argument-hint: "[무엇을 만들/바꿀지 한 줄 — 비우면 직전 대화의 요청을 사용]"
---

# /ai-dlc-request — AI-DLC 워크플로 진입점

새 소프트웨어 개발 요청을 **CLAUDE.md의 AI-DLC 적응형 워크플로**로 시작한다.
일반 기능 추가/변경의 "정문(front door)"이다.
(동작 보존 재설계는 `/ai-dlc-refactor`, 기능 폐기는 `/ai-dlc-deprecate`를 쓴다.)

요청 내용: $ARGUMENTS
(비어 있으면 직전 대화 맥락의 요청을 대상으로 삼는다.)

## 진행 절차

CLAUDE.md의 INCEPTION → CONSTRUCTION 흐름을 그대로 따른다. 요약하면:

1. **룰셋 로드.** 다음 경로 중 먼저 존재하는 것을 쓴다(이 프로젝트는 `.aidlc-rule-details/`):
   `.aidlc/aidlc-rules/aws-aidlc-rule-details/` → `.aidlc-rule-details/` →
   `.kiro/aws-aidlc-rule-details/` → `.amazonq/aws-aidlc-rule-details/`.
   - `common/process-overview.md`, `common/session-continuity.md`,
     `common/content-validation.md`, `common/question-format-guide.md`를 로드.
   - `extensions/` 하위의 `*.opt-in.md`만 가볍게 로드(전체 룰은 opt-in 후 로드).

2. **Welcome 메시지 1회 표시.** `common/welcome-message.md`를 로드해 처음 한 번만 보여준다.

2.5. **트랙 생성 (동시 다중 트랙).** `common/concurrent-tracks.md`를 로드하고 따른다.
   - 새 **Track ID** 부여(기존 최대 +1, 예: `F9`).
   - `aidlc-docs/tracks/_TEMPLATE/`를 `aidlc-docs/tracks/<id>/`로 복사해 `state.md`/`audit.md` 생성.
   - 루트 `aidlc-docs/aidlc-state.md`의 **Track Registry** 테이블에 행 추가(`active`).
   - **worktree 게이트**: 실제 코드 생성(Code Gen Part 2) 전에 반드시
     `git worktree add .claude/worktrees/<track> -b feat/<track>`. `main`에서 코드 변경 금지.
     서브모듈(`operator-console/cli`)을 건드리면 그 안에서도 `feat/<track>` 브랜치를 따고,
     부모 gitlink는 **머지 시점에만** 커밋. (설계/문서 단계는 worktree 전이라도 진행 가능.)

3. **요청 기록.** 사용자의 **원문 그대로**를 **그 트랙의** `aidlc-docs/tracks/<id>/audit.md`에
   append(루트 audit.md 아님; 덮어쓰기 금지).

4. **Workspace Detection (항상).** `inception/workspace-detection.md` 실행.
   - 루트 `aidlc-state.md`의 Track Registry에 **진행 중(active) 트랙**이 있으면 → 새 요청이 아니라
     재개일 수 있으니 알리고 **`/ai-dlc-resume` 제안**.
   - 코드 존재 여부로 brownfield/greenfield 판정.

5. **Reverse Engineering (brownfield + 아티팩트 없을 때만).** `inception/reverse-engineering.md`.

6. **Requirements Analysis (항상, 적응형 깊이).** `inception/requirements-analysis.md`.
   - 모호하면 **질문 파일을 한국어로** 생성(`question-format-guide.md` 형식, A/B/C/D + Other).
   - 답변 게이트를 통과하기 전엔 다음 단계로 넘어가지 않는다.
   - extension opt-in 질문도 여기서 함께 제시.

7. **이후 조건부 단계** (User Stories / Workflow Planning / Application Design /
   Units Generation → Construction의 Functional/NFR/Infra Design → Code Generation →
   Build & Test)를 요청 복잡도에 맞춰 적응적으로 실행. 각 단계는 **2-옵션 승인 게이트**
   (변경 요청 / 계속)로 마무리하고, 사용자 응답을 audit.md에 기록한다.

## 운영 규칙 (CLAUDE.md 준수)

- 모든 사용자 입력/승인은 **그 트랙의** `tracks/<id>/audit.md`에 **append**(요약 금지, ISO 8601).
  루트 `audit.md`는 **머지 시점 한 줄 요약**만.
- 질문/계획/설계 문서는 **한국어**가 기본.
- 애플리케이션 코드는 **트랙 worktree** 안에서만 생성(루트 `main` 트리에 코드 변경 금지).
  문서는 `aidlc-docs/`에만.
- 설계 승인 후 Construction(코드+테스트)은 **자율 진행**하고, 진짜 사람 판단이 필요할 때만 멈춘다.
- 진행 상황은 **트랙의** `aidlc-docs/tracks/<id>/state.md`와 각 plan 체크박스에 **즉시** 반영
  (루트 `aidlc-state.md`는 Track Registry 행만, 생성/종료 때만 갱신).
