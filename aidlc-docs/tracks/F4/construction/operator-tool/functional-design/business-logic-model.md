# 비즈니스 로직 모델 — Unit B `operator-tool` (F4, opencode 하드 fork)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit B · Functional Design · 2026-05-30._

운영자 입력이 file-drop 명령이 되기까지의 흐름, 읽기/이벤트 흐름, 그리고 fork 전략을 정의한다.
(데몬측 처리는 Unit A 소관. 여기는 *생산자/소비자* 측만.)

## 1. 입력 → 명령 흐름 (3 경로)

### 1.1 결정적 경로 (매매/제어 기본, Q2=A)
```
/sell AAPL 50%  또는 키스트로크
  → 결정적 파서: verb=sell, args={symbol:AAPL,size:50,unit:%}  (LLM 미개입)
  → echo "SELL 50% AAPL @ market" + risk_preview(추정, 라이브 아님)
  → ConfirmationGate [y/N]  (파괴적이면 CONFIRM)
       거부/타임아웃 → no-op
       통과 → token(env) 부착 → SteeringCommand(confirmed=True) → steering/commands.jsonl append (원자적)
  → OutcomeWaiter: id로 events.jsonl outcome 매칭 표시
```
- **fork 이점(B′)**: 이 경로는 **TUI 레벨에서 LLM을 완전히 우회**한다. 슬래시/키스트로크 매매는 프롬프트로
  가지 않으므로 비결정성 0(무-fork였다면 슬래시가 프롬프트라 불가능했던 부분).

### 1.2 자연어 경로 (편의, Q4=B 정책)
```
"애플 절반 팔자"  → LLM이 CommandDraft 제안(verb/args) → 동일 ConfirmationGate
```
- LLM은 **Draft까지만**. `confirmed`/token 부여·append는 **결정적 레이어**가 사람 확인 후 수행(LLM 위조 불가).

### 1.3 조회 경로 (읽기, Q3=A)
```
/status, /positions, /orders, /agent-trace, /why
  → 결정적 읽기: snapshot.json / journal / scripts/agent_trace.py → 패널·텍스트 렌더 (데몬 라운드트립 0)
```

## 2. 이벤트/알림 흐름 (Q4=A)
```
[Unit A] steering/events.jsonl (append-only)
   └─ Unit B 백그라운드 tail(goroutine) → NotificationInbox
        ├ outcome(corr_id) → OutcomeWaiter 해소(체결/거부/…)
        ├ pending/fill → push 알림(토스트) + 패널 갱신
        ├ agent_question → AgentQuestionItem(inbox) + push
        └ reconcile → 상태 표시
snapshot.json 폴(또는 watch) → SnapshotView → 상시 패널(포지션/주문/run_state)
```

## 3. 양방향 질의 (Q6-E)
```
agent_question 이벤트 → inbox 표시 → 운영자 /answer <id> <text>
  → SteeringCommand(verb=answer, token) → [Unit A] agent_answers.jsonl + reconcile → 다음 turn에서 agent 반영
```

## 4. 검증/환원 규칙 (운영자 측, 결정적)
- 슬래시/키스트로크 파싱은 Unit A 검증과 **동일 규약**: 심볼 대문자; size 단위 `$`/`sh`/`%`(sell만 %);
  단위 누락/불가 → 거부+사유. **부분 실행 금지**(fail-closed).
- NL 환원 결과도 **같은 파서/검증**을 통과해야 Draft가 된다(LLM이 만든 args도 결정적 검증).
- 토큰은 매 명령에 env에서 읽어 부착; **화면/로그 미표시**(SECURITY-03).

## 5. fork 전략 (B′ — 무엇을 유지/제거/추가; FD 고도, 상세는 NFR/Code-Gen + 스파이크)
- **추가**: (a) 트레이딩 패널들(positions/orders/P&L, pending-approvals, event feed) — Go TUI(Bubble Tea) 위젯;
  (b) 결정적 명령 경로(1.1) — 입력 인터셉트 → 파서 → ConfirmationGate 모달 → file-drop writer; (c) events tail
  goroutine + snapshot 폴; (d) `steer` 결정적 액션(토큰/append 소유); (e) NL→Draft는 LLM 경유(1.2).
- **제거(컴파일타임, Q1=B′ 핵심 보안)**: 코딩 에이전트 도구 중 **`task`(서브에이전트, #5894), 파일 write/edit, 임의
  bash, web**을 **소스에서 제거/비활성** → 권한 설정 버그(#6396)에 의존하지 않고 **구조적으로 side-effect 도구는
  `steer`(+읽기) 하나만** 남긴다. (무-fork였다면 permission deny에 의존해야 했던 부분을 fork로 봉쇄.)
- **리브랜딩**: 바이너리명(예 `autostock-console`)/스플래시/시스템프롬프트 내장; 모델/auth 핀.
- **업스트림**: 가져온 시점 baseline 고정(추적 안 함), 보안 패치만 선별 반영. 라이선스 준수(Q7=A).
- **계약 불변**: file-drop(commands/events/snapshot) + 토큰만이 데몬과의 인터페이스 — fork해도 Unit A 무변경.

## 6. 안전 경계 (재확인)
운영자 콘솔(LLM 포함)이 전부 뚫려도 최종 안전은 **데몬측 Unit A**: `confirmed`+토큰 검증 + RiskManager→Broker
게이트 + 에이전트 advisor-only(PreToolUse 훅). Unit B의 결정적 경로·컴파일타임 도구 제거는 **defense-in-depth**.
