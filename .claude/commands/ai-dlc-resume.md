---
description: AI-DLC 작업을 aidlc-state.md 기준 중단점부터 재개
argument-hint: "[선택: 특정 unit/stage 이름 — 비우면 state가 가리키는 다음 단계]"
---

# /ai-dlc-resume — 중단점부터 재개

이전 세션에서 진행하던 AI-DLC 작업을 **상태 파일 기준으로 이어서** 진행한다.

재개 대상: $ARGUMENTS
(비어 있으면 `aidlc-state.md`가 가리키는 다음 미완료 단계.)

## 진행 절차

1. **세션 연속성 규칙 로드.** 룰셋 디렉터리(`.aidlc-rule-details/`)에서
   `common/session-continuity.md`와 `common/process-overview.md`를 로드한다.

2. **상태 파악.** 다음을 읽고 현재 위치를 재구성한다:
   - `aidlc-docs/aidlc-state.md` — 완료/스킵/진행 중 stage, Extension Configuration.
   - `aidlc-docs/audit.md`의 **최근 항목** — 마지막 사용자 입력·승인·다음 액션.
   - 진행 중 stage의 plan 파일 체크박스(`aidlc-docs/construction/<unit>/...`,
     `aidlc-docs/inception/.../plans/...`) — 어느 step까지 [x]인지.
   - `/ai-dlc-refactor` 작업이면 `aidlc-docs/inception/refactor/<name>/2-tier-ledger.md`의
     정지 지점(특히 미해결 T3 항목).

3. **재개 지점 요약 제시.** 사용자에게 2~4줄로:
   - 지금 어느 phase/stage/unit에 있는지,
   - 마지막으로 완료한 것과 **바로 다음에 할 일**,
   - 사용자 입력 대기 중인 게이트(미응답 질문·미승인 단계)가 있으면 명시.

4. **게이트 확인.** 다음 단계가 **승인 대기**거나 **미응답 질문**이면, 자동 진행하지 말고
   해당 질문/승인을 다시 제시하고 멈춘다. 그 외에는 CLAUDE.md 워크플로대로 이어서 진행한다.

5. **기록.** 이 재개 호출과 사용자 응답을 `aidlc-docs/audit.md`에 append.

## 주의

- 상태가 모순되거나(예: state는 완료인데 plan 체크박스는 미완) 애매하면 **추측하지 말고**
  무엇을 다음으로 할지 사용자에게 확인한다.
- `aidlc-state.md`가 아예 없으면 재개할 작업이 없는 것 — `/ai-dlc-request`로 새로 시작하라고 안내.
