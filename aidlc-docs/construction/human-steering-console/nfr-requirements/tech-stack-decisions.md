# 기술 스택 결정 — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · NFR Requirements (minimal) · 2026-05-29._

**UI 우선 결정(2026-05-29, CQ-NFR1=B, CQ-NFR2=A):** "신규 런타임 의존성 0"은 hard 요구가 아니었고, UX 지향
(seamless·이쁨·claude cli 느낌)을 위해 **`prompt_toolkit` + `rich` 2개를 신규 런타임 의존성으로 채택**한다.
그 외 신규 의존성은 두지 않는다. textual 풀 TUI는 채택 안 함(v1 = 라인 REPL을 monitor.sh 패널에 유지).

---

| 관심사 | 결정 | 비고 |
|---|---|---|
| 언어 | Python 3.11+ (기존) | — |
| REPL 입력/UI | **`prompt_toolkit`** — 데몬 전용 스레드에서 `prompt_toolkit` 세션 실행 + 손수 만든 슬래시-명령 파서. 슬래시/심볼 자동완성(`Completer`), 히스토리, 하단 툴바(상태·승인대기 라이브), **`patch_stdout`로 async 알림이 입력 줄을 안 깨뜨림**(CQ2=A 핵심). `cmd.Cmd` 미사용. | **신규 런타임 의존성(1)** |
| 출력 포맷 | **`rich`** — `/status`·`/positions`·`/orders` 테이블, 색/패널, 한 줄 결과 요약. 가능하면 prompt_toolkit과 함께(rich 출력은 patch_stdout 영역으로). | **기존 의존성**(`rich>=13.0.0`, scripts/status.py가 이미 사용) |
| 동시성/직렬화 | stdlib `threading`(Lock/Event) ± `queue.Queue` — 단일 직렬화 경로(NFR-1). 최종 프리미티브는 NFR Design에서. | 콘솔·스케줄러·reconcile 공유 |
| 스케줄러 | 기존 `TradingScheduler`(APScheduler) — 콘솔과 직렬화되도록 잡 실행을 명령 락과 결합. | 신규 의존성 없음 |
| LLM 세션 | 기존 `AgentSession`(`claude -p`) 재사용 — reconcile 턴은 turn-lock 하에 호출, 모델=세션 기본(sonnet) 별도 지정 없으면. | 신규 의존성 없음 |
| 레코드 직렬화 | **pydantic**(기존) — `InterventionRecord`/`PendingApproval`/`Directive`. JSONL을 workspace에 저장(저널 관례 일치). 안전 역직렬화(SECURITY-13). | 신규 의존성 없음 |
| 주문 경로 | 기존 `DecisionExecutor`→`RiskManager`→`Broker` 재사용(신규 경로 없음, Q6=A). | — |
| 로깅 | 기존 loguru — 콘솔 부착 시 stdout 싱크 제거, 파일 싱크 유지(Q3=A). | 신규 의존성 없음 |
| 테스트/PBT | **Hypothesis**(이미 dev 의존성, PBT-09) + pytest. | 신규 런타임 의존성 아님 |
| 실행/런치 | `scripts/monitor.sh`에 데몬+콘솔 패널 추가(CQ5=A). tmux(기존) 활용. | 신규 의존성 없음 |

## 결론
- **신규 런타임 의존성: `prompt_toolkit` 1개** — UX 지향을 위해 채택(CQ-NFR1=B). `rich`는 **이미 의존성**
  (`rich>=13.0.0`, scripts/status.py가 사용), `hypothesis`도 이미 dev. `prompt_toolkit`만 `pyproject.toml`에
  고정 버전 추가(SECURITY-10 — lock/핀). 그 외는 기존 의존성 재사용.
- textual 풀 TUI는 v1 비채택(CQ-NFR2=A). 단 rich 출력·명령 모델은 추후 textual 승격 시 재사용 가능.
- 미확정(설계로 이월): 직렬화 프리미티브(Lock vs queue 워커)·스케줄러 단일-워커 구성, 그리고 **prompt_toolkit
  이벤트 루프를 데몬 스레드에서 돌리는 방식 + patch_stdout과 직렬화 경로의 상호작용** — **NFR Design**에서 결정.
