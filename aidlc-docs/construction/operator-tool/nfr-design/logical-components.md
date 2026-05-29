# 논리 컴포넌트 — Unit B `operator-tool` (F4, opencode 하드 fork)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit B · NFR Design · 2026-05-30._
_fork 위에 추가/수정/제거할 컴포넌트(코드젠 단위 경계). 정확한 파일 경로는 스파이크에서 확정._

## 추가 (우리 코드)
### Go (TUI) 측 — `autostock-console`
| 컴포넌트 | 책임 |
|---|---|
| `panels/positions` | PositionsPanel — SnapshotView 렌더(보유/주문/락/P&L) |
| `panels/eventfeed` | EventFeedPanel + push 토스트(EventMsg) |
| `panels/pending` | PendingPanel(승인 대기) |
| `panels/statusbar` | run_state/market/token/clock |
| `command/parser` | 결정적 슬래시·키스트로크 → CommandDraft(검증, Unit A 규약) |
| `command/confirm` | ConfirmModal(echo+risk_preview, `[y/N]`/`CONFIRM`) — confirm 무결성 소유 |
| `filedrop/writer` | 토큰 부착 + `commands.jsonl` 원자 append; OutcomeWaiter(corr_id) |
| `filedrop/tail` | events.jsonl tail goroutine → EventMsg; snapshot poll → SnapshotMsg |
| `inbox/questions` | QuestionInbox + `/answer` |

### TS (코어) 측
| 컴포넌트 | 책임 |
|---|---|
| `steering-schema.ts` | E7/E8/snapshot 타입 미러(Unit A 권위) |
| `tools/steer`(폴백) | P-B2 폴백 시: 결정적 execute(confirm/토큰/append). 기본 경로는 Go writer |
| NL 경로 | LLM이 CommandDraft *제안*만 client로 반환(쓰기 권한 없음) |

## 수정 (fork 베이스)
- **도구 레지스트리**: `task`/`bash`(임의)/`edit`/`write`/`webfetch`/web **등록 제외**(P-B3). side-effect=`steer`+읽기만.
- **리브랜딩**: 바이너리명(`autostock-console`)/스플래시/시스템프롬프트 내장; 모델·auth 핀.
- **client↔server**: P-B2 "제안-only" 흐름 배선(가능 시) — NL Draft를 client confirm으로.

## 제거 (컴파일타임)
- 위 side-effect 도구들 + 불필요한 코딩-에이전트 기능(스파이크에서 안전 제거 범위 확정).

## 외부 계약 (Unit A — 불변)
- `steering/commands.jsonl`(write), `steering/events.jsonl`(tail), `steering/snapshot.json`(read), env 토큰.
- 스키마 권위 = Unit A pydantic; 동기 = `steering/contract-samples/` 골든 + 양측 계약 테스트(P-B4).

## 스레드/프로세스 모델
```
[운영자 프로세스 = autostock-console (fork)]
  Bun TS 코어(에이전트/LLM/도구레지스트리[봉쇄됨])  ←client/server→  Go TUI(Bubble Tea 단일 루프)
                                                                      ├ command/parser → ConfirmModal → filedrop/writer (토큰+append)
                                                                      ├ filedrop/tail goroutine → EventMsg
                                                                      └ snapshot poll goroutine → SnapshotMsg
   (NL: TS LLM → CommandDraft 제안 → TUI ConfirmModal → Go writer)        토큰: process.env (쓰기 게이트)

      │ file-drop (repo-root steering/)                            ▲ events/snapshot
      ▼                                                            │
[데몬 프로세스 = main.py --mode agent --steering]  Unit A: 검증+토큰+RiskManager→Broker (최종 안전 경계)
```

## 빌드/실행 (스파이크에서 확정)
- Bun(TS) + Go 빌드 → 단일 바이너리 또는 `bun`/`go run`. lockfile 핀(SECURITY-10). 운영자 머신 로컬, 데몬과 같은 env(토큰 상속).

## 테스트 전략
- Go: parser/confirm/writer(토큰 부착, 원자 append) 단위 + 도구 레지스트리 봉쇄 단언.
- TS: 스키마 미러 round-trip + (폴백 시) steer execute.
- **계약 테스트(cross-language)**: 골든 샘플 양측 파싱/생산 일치.
- 통합(스파이크 후): 콘솔 → commands.jsonl → (로컬 데몬/시뮬) → events outcome 왕복.

## 코드젠 진입 = 스파이크 먼저 (NFR Requirements §6)
정식 레포/태그 · custom tool/제안-only 흐름 · 도구 레지스트리 위치 · 커스텀 pane PoC · 빌드. 결과로 P-B2/P-B3 형태 + 본 컴포넌트 경로 확정.
