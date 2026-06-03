# NFR 설계 패턴 — Unit B `operator-tool` (F4, opencode 하드 fork)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit B · NFR Design · 2026-05-30._
_입력: `../nfr-requirements/` + `../functional-design/`._

> **⚠ 스파이크(2026-05-30) 정정:** 현행 sst/opencode는 **순수 TS/Bun + OpenTUI(JSX)** — **Go 아님.** 아래 P-B1의 "Bubble Tea/
> goroutine" 표현은 **OpenTUI(JSX 컴포넌트) + TS async(타이머/async 워커가 상태 갱신)**로 읽으세요. 패널/모달/토스트는 **TuiPlugin
> API**(`render`/`replace`/`toast`), 도구 제거는 **`registry.ts`**, **P-B2는 in-process라 기본안 확정**(TuiPlugin이 입력→confirm→
> write 소유; LLM tool은 제안만; 폴백 불필요). "goroutine"→"async 워커", "Go writer"→"TS writer"로 대응.

## P-B1. 동시성 — Bubble Tea 단일 update 루프 + 백그라운드 메시지 소스
- Go TUI는 Elm식 **Model-Update-View 단일 루프**(상태 변이는 `Update`에서만). 부수효과/백그라운드는 **goroutine이 `tea.Msg`를
  `program.Send()`로 주입** → `Update`가 처리(모델 직접 변이 금지).
- 백그라운드 소스:
  - **events-tail goroutine**: `steering/events.jsonl`를 watch/tail → `EventMsg` 주입(fill/pending/agent_question/outcome).
  - **snapshot-poll goroutine**: `snapshot.json`(2–5s) → `SnapshotMsg`.
  - 둘 다 torn-safe 읽기(완전 라인/완전 JSON만; 부분이면 다음 틱).
- → TUI 렌더(패널/피드/토스트)는 항상 메인 루프에서, 레이스 없음.

## P-B2. 단일 결정적 쓰기 경로 — confirm 무결성 (핵심, fork 이점)
- **쓰기(매매/제어)는 Go 클라이언트가 소유**: 입력 → 결정적 파서 → `ConfirmModal`(Update 상태) → 사람 `y`/`CONFIRM`
  키 → `tea.Cmd`가 **토큰 부착 + `commands.jsonl` append**. LLM(TS) 미경유.
- **자연어 경로**: TS 코어 LLM은 **`CommandDraft` *제안*만** 반환(=client에 메시지). client는 그 Draft를 **동일 `ConfirmModal`**로
  보내고, 확인 후 **Go가 직접 write**. → LLM은 절대 `commands.jsonl`/토큰/`confirmed`에 손대지 않음(위조·우회 불가).
- **⚠ 스파이크 확인 항목:** opencode client↔server 프로토콜이 "LLM tool이 *결과를 client로 제안만* 하고 client가 실행"하는
  흐름을 허용하는지. 불가 시 폴백: TS `steer` plugin tool의 `execute`가 confirm/토큰/append를 소유(여전히 결정적 코드, LLM은
  호출만) — confirm은 그 execute가 stdin/UI로 직접 수행. 어느 쪽이든 **결정적 레이어가 confirm을 소유**(BR-B1).

## P-B3. 컴파일타임 도구 봉쇄 (BR-B4, SECURITY-11)
- opencode 도구 레지스트리(TS)에서 **`task`/`bash`(임의)/`edit`/`write`/`webfetch`/web을 빌드에서 제외**, side-effect는
  `steer`(쓰기) + 읽기 도구만 등록. 권한 설정(deny)에 의존하지 않음 → #5894(서브에이전트 우회)/#6396(SDK deny 무시) **구조적 불가**.
- **검증 테스트**: fork 빌드의 등록 도구 집합 == 허용목록(제거 대상 부재)을 단언. (⚠ 레지스트리 위치는 스파이크에서 확정.)

## P-B4. 스키마 동기 / 계약 (cross-language)
- Unit A pydantic(E7/E8/snapshot)이 **권위**. TS 타입은 **수기 미러**(`steering-schema.ts`).
- **계약 테스트**: `steering/contract-samples/`에 정전(canonical) JSON 샘플 — Unit A 테스트가 pydantic으로, Unit B 테스트가 TS로
  **양쪽 파싱·왕복**을 단언. 스키마 변경 시 한쪽만 고치면 계약 테스트가 깨져 잡힌다.
- verb/단위 검증 규약(symbol 대문자, `$`/`sh`/`%`(sell만), 단위누락 거부)을 TS 파서가 동일 구현 + 샘플로 고정.

## P-B5. file-drop 쓰기/읽기 (TS/Go)
- **append**: `O_APPEND` 단일 write(개행 종료) — 작은 라인은 원자적. 초과/경합 시에도 Unit A가 torn-line·id-dedup으로 흡수
  (BR-11). 즉 운영자=단순 append, 데몬=완전 라인만 소비(이미 구현).
- **읽기**: events tail은 바이트 오프셋 추적(마지막 표시 위치), snapshot은 완전 JSON만(부분이면 직전 값 유지).
- 경로는 repo-root `steering/`(BR-B9, Unit A 소유 경로).

## P-B6. 토큰 (BR-B2, SECURITY-03)
- 부팅 시 `process.env.STEERING_OPERATOR_TOKEN` 읽기. 없으면 **쓰기 UI 비활성 + 상태바 빨강**(읽기 패널은 동작).
- 화면/로그/이벤트에 토큰 미표시. 명령 직렬화 시에만 `token` 필드에 주입.

## P-B7. 회복성
- events-tail/snapshot-poll/파일쓰기 실패 → `ErrorMsg` → 상태바·토스트 경고. **TUI를 죽이지 않음**(best-effort).
- 콘솔 크래시/종료는 데몬 무영향(별 프로세스 — Unit A NFR). 토큰/데몬 미연결이면 안전하게 읽기 전용.
- 명령 outcome 타임아웃 → "결과 미수신" 경고(데몬 지연·미동작 가시화, BR-B6).

## P-B8. 보안 패턴 (강제)
- **SECURITY-11**: P-B2(단일 결정적 쓰기 경로) + P-B3(컴파일타임 봉쇄) + 데몬측 최종 게이트(Unit A) defense-in-depth.
- **SECURITY-10**: opencode baseline + TS/Go deps lockfile 핀, MIT 고지 유지.
- **SECURITY-03**: P-B6. **SECURITY-15**: 파서/confirm fail-closed, 백그라운드 best-effort.

## 패턴 ↔ 규칙/NFR 추적
| 패턴 | 충족 |
|---|---|
| P-B1 단일 루프 + 메시지 소스 goroutine | 동시성/가용성 |
| P-B2 단일 결정적 쓰기 경로 + LLM 제안-only | BR-B1/B3, confirm 무결성 |
| P-B3 컴파일타임 봉쇄 | BR-B4, SECURITY-11, #5894/#6396 |
| P-B4 스키마 미러 + 계약 테스트 | BR-B9 cross-language |
| P-B5 append/torn-safe 읽기 | BR-B6, Unit A BR-11 정합 |
| P-B6 토큰 | BR-B2, SECURITY-03 |
| P-B7 회복성 | BR-B8, SECURITY-15 |

## 스파이크-의존 요약 (NFR Requirements §6에서 확정)
client↔server "제안-only" 흐름 가능성(P-B2 폴백 결정) · 도구 레지스트리 위치(P-B3) · 커스텀 pane 추가법(P-B1) ·
정식 레포/태그. 스파이크 결과로 P-B2/P-B3 구현 형태를 확정한다.
