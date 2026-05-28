# NFR 요구사항 — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · NFR Requirements (minimal) · 2026-05-29._
_상위 NFR은 `inception/requirements/human-steering-console.md §4`에서, 규칙 매핑은 `functional-design/business-rules.md`에서 이어짐._

> 이 단계는 minimal로 실행. NFR 목표와 기술 스택이 이전 답변(Q9/Q10 익스텐션, "신규 런타임 의존성 0",
> NFR-1 동시성, 보안 강제)으로 이미 확정되어 별도 질문 라운드 없이 정리만 한다.

---

## NFR-목표 요약 (단일 운영자 · 로컬 데몬 맥락)

| 영역 | 목표 | 근거/메모 |
|---|---|---|
| **성능** | 읽기/파싱 명령은 체감 즉시. 거래는 브로커 레이턴시에 종속. reconcile는 async라 콘솔을 절대 블록하지 않음. | 단일 운영자·저빈도 입력 → 고처리량 불필요. |
| **확장성** | 별도 확장 요구 없음(단일 데몬·단일 사용자). 승인대기 큐/락 집합은 소규모. | N/A에 가까움. |
| **가용성/신뢰성** | 콘솔 장애가 거래에 영향 없음(스레드 격리, BR-8.2). reconcile best-effort(BR-6.3). 비-TTY 자동 비활성화(BR-8.3). | 데몬 연속성 최우선. |
| **동시성(핵심, NFR-1)** | 콘솔 변이·스케줄러 잡·reconcile 턴이 단일 직렬화 경로 통과 → 브로커/executor 커서/CLI 세션 레이스 0. | 구체 설계는 NFR Design. |
| **보안(강제)** | SECURITY-03(로그 비밀정보 0)/11(스티어링·주문배치 분리, 방어심층, 오남용 확인)/13(append-only 감사, 안전 역직렬화)/15(fail-closed). **SECURITY-10**: 신규 의존성 `prompt_toolkit`(rich는 기존)을 `pyproject.toml`에 고정 버전으로(lock/핀). 그 외 N/A(로컬 CLI). | `business-rules.md` 컴플라이언스 매핑. |
| **유지보수성** | 기존 `DecisionExecutor`/`RiskManager`/`Journal` 재사용, 신규 주문 경로 없음. PBT+예제 테스트. | 표면적 최소화. |
| **사용성(UX)** | `frontend-components.md`의 한국어 프롬프트/확인/도움말/에러 메시지. **UI 스택: `prompt_toolkit` + `rich`**(CQ-NFR1=B) — 자동완성·히스토리·하단 툴바·patch_stdout·rich 테이블. | 사용자 지침: UX 구체화. seamless 우선. |

## 상태 영속성 요구
- `human_locks.json`, `pending_approvals.jsonl`, `directives.jsonl` — workspace 내, **ET 날짜 스코프**(같은 날
  재시작 복원, 다음 거래일 자동 해제). pydantic 직렬화.
- `RunState`(pause/halt) — **ET-date 영속**(`run_state.json`, CQ-D1=A): 같은 거래일 재시작 시 복원, 다음 거래일 자동 running.
- `human_directives.jsonl` — append-only 영구 감사 로그(날짜 무관 누적).

## 신뢰성 세부
- 콘솔 스레드 예외 격리(try/except, 락 finally 해제) → 데몬 비중단.
- reconcile 턴 실패는 로그만(데몬 비중단), 디바운스로 LLM 세션 충돌·과호출 방지.
- fail-closed: 파싱/확인 실패 시 부분 실행 금지.

## 테스트 NFR (PBT 부분 강제 — Q10=B)
- 프레임워크: **Hypothesis**(이미 dev 의존성, PBT-09). 러너: pytest.
- 속성: 파서 불변식·락 상태머신 불변식(PBT-03), 레코드 라운드트립(PBT-02), 생성기/시드 재현(PBT-07/08).
- 예제(PBT-10): CONFIRM/kill/paused 스킵/게이팅/보호 예외/reconcile 실패 내성.
- 무회귀: 기존 196 테스트 그린 유지(NFR-5).
