# 비즈니스 규칙 — Unit B `operator-tool` (F4, opencode 하드 fork)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit B · Functional Design · 2026-05-30._

## BR-B1 confirm 무결성 (핵심)
- BR-B1.1 매매/라이프사이클/승인/`/answer` 등 **쓰기 명령은 결정적 레이어가 확인을 소유**한다(Go TUI 모달 또는
  `steer` tool execute). LLM은 `CommandDraft`까지만 — `confirmed`/token을 부여·위조할 수 없다.
- BR-B1.2 `[y/N]`(기본 N); 파괴적(`flatten_all`/`kill`)은 `CONFIRM` 키워드. 거부/타임아웃/빈입력 → no-op(fail-closed).
- BR-B1.3 통과한 명령만 `confirmed=True`로 승격 → 토큰 부착 → commands.jsonl **원자적 append**.

## BR-B2 토큰 취급 (BR-10.2 준수, Q5=A)
- env `STEERING_OPERATOR_TOKEN`에서 읽어 매 `SteeringCommand.token`에 부착. **화면/로그/파일에 미표시**(SECURITY-03).
- 토큰 부재 시: 쓰기 명령 비활성 + "데몬과 미연결(토큰 없음)" 경고(읽기 패널은 동작).

## BR-B3 주문 경로에 LLM 권한 없음
- LLM은 NL→Draft 제안만. 토큰·confirm·append·실행 권한 없음. 슬래시/키스트로크 매매는 **LLM 우회**(fork, 1.1).
- 콘솔은 **제2 주문 경로를 만들지 않는다** — 오직 file-drop에 쓰고, 실행은 데몬(Unit A) RiskManager→Broker.

## BR-B4 컴파일타임 도구 봉쇄 (Q1=B′ 핵심 보안)
- fork 빌드에서 **side-effect 도구를 `steer`(쓰기) + 읽기 도구로 한정**하고, `task`(서브에이전트)·파일 write/edit·
  임의 bash·web을 **소스에서 제거/비활성**. 권한 설정(deny)에만 의존하지 않음 → #5894/#6396이 **구조적으로 불가**.
- 검증(테스트): fork 빌드에 제거 대상 도구가 등록돼 있지 않음을 고정.

## BR-B5 검증/환원 (결정적, fail-closed)
- 슬래시/키스트로크/NL 환원 모두 **동일 결정적 파서**(Unit A 규약): 심볼 대문자; size 단위 `$`/`sh`/`%`(`%`는 sell만);
  단위 누락·불가 → 거부+사유, 부분 실행 금지.

## BR-B6 결과/이벤트 (Q4=A)
- 보낸 명령은 `id`로 outcome(`corr_id`) 매칭 표시; 타임아웃 시 "결과 미수신" 경고.
- events.jsonl 백그라운드 tail: pending/fill/agent_question은 push 알림, 전체는 피드 패널. 이벤트는 읽기 전용(Unit A 소유).

## BR-B7 읽기 (Q3=A, 무해)
- status/positions/orders/agent-trace/why는 `snapshot.json`/journal/`scripts/agent_trace.py`를 **결정적으로 읽어** 표시.
  데몬 라운드트립·토큰 불필요(부수효과 0).

## BR-B8 가용성/격리
- 콘솔 크래시·미실행이 데몬 트레이딩에 영향 없음(데몬은 file-drop을 아무도 안 써도 정상 — Unit A NFR). 
- tail/폴 실패는 패널 경고로만, 콘솔을 죽이지 않음(best-effort).

## BR-B9 계약 준수 (Unit A 무변경)
- 생산/소비 스키마(E7 `SteeringCommand`, E8 `SteeringEvent`, snapshot)는 **Unit A 소유** — Unit B는 준수만.
  경로는 repo-root `steering/`(commands/events/snapshot). fork해도 이 계약은 불변.

## 컴플라이언스 매핑
- **SECURITY-11**: BR-B1(confirm 무결성)·BR-B3(주문경로 분리)·BR-B4(컴파일타임 봉쇄). **SECURITY-03**: BR-B2(토큰 미표시).
- **SECURITY-13**: 환원 결과는 E7 스키마로 직렬화(안전). **SECURITY-15**: BR-B1.2/BR-B5 fail-closed.
- **SECURITY-10**: 베이스(opencode fork) + 플러그인/의존성 버전 핀; 라이선스 준수(Q7=A).
- **PBT(부분)**: 결정적 파서/환원·토큰부착·confirm 승격 불변식 example 테스트(TS 측).
