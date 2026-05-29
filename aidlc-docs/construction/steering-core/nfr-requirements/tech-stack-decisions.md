# Tech-Stack 결정 — Unit A `steering-core` (F4)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit A · NFR Requirements · 2026-05-29._

| 관심사 | 결정 | 신규 의존성 |
|---|---|---|
| 명령/이벤트/질문 레코드 | `pydantic`(재사용) | 0 |
| 동시성(CommandWorker/turn_lock/state_lock) | stdlib `threading`(+ `queue`) | 0 |
| file-drop 폴링 | 기존 `APScheduler` 잡(재사용, Q3=A) | 0 |
| torn-safe JSONL 리더 + 바이트오프셋 커서 | stdlib(`open`/seek/tell) | 0 |
| 원자적 파일 쓰기(snapshot/cursor) | stdlib `os.replace`(temp+rename) | 0 |
| 주문 경로 | 기존 `DecisionExecutor`/`RiskManager`/`Broker`(`_execute_one`→공개 `execute_decision`) | 0 |
| 로깅 | 기존 `loguru` | 0 |
| 테스트 | `pytest` + `Hypothesis`(이미 dev 의존성) | 0 |

## BR-10.1 PreToolUse 훅 (에이전트=claude 측) — 기술 방식
- **무엇:** `AgentSession`이 띄우는 `claude -p`가 로드하는 **settings.json에 PreToolUse 훅**을 등록해
  `Read/Write/Edit/Glob/Grep/Bash`의 **`workspace/` 밖 경로 접근을 거부**(결정적 스크립트가 input의 경로를 검사해 deny 반환).
- **형태:** 훅 스크립트는 **Python(레포 재사용·단위테스트 가능)**, settings.json은 코드젠이 생성/배치.
- **위치(검증 항목):** `claude -p`(cwd=`workspace/`)가 훅을 로드하도록 `workspace/.claude/settings.json`에 배치
  (대안: 프로젝트/유저 settings, `--settings` 플래그 — 코드젠에서 실측). `--permission-mode dontAsk`여도 훅 hard-deny 유효.
- **토큰(BR-10.2):** 파일/데몬 env 비저장. 운영자(Unit B) 프로세스 env로만 전달, 에이전트 spawn 시 env scrub. 신규 의존성 0.

## opencode (Unit B) — 여기서는 범위 밖
opencode 의존성/버전 핀(SECURITY-10), 권한·플러그인 구성, confirm 무결성은 **Unit B NFR Requirements**에서.
사전 조사: `../../operator-tool/nfr-requirements/opencode-feasibility.md` (충분, 조건부).

## 요약
Unit A는 **순수 stdlib + 기설치 의존성**으로 구현 가능(신규 런타임 의존성 0). 새 무게는 *코드*가 아니라
*동시성·권한 분리의 정확성*에 있다 — NFR Design에서 패턴으로 확정.
