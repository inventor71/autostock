# NFR Requirements — Unit A `steering-core` (F4)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit A · NFR Requirements (minimal) · 2026-05-29._
_입력: requirements `steering-console-redesign.md` §6 NFR + Unit A Functional Design + /critic 반영._

## 결론: **Unit A 신규 런타임 의존성 0** (F2가 추가하던 `prompt_toolkit`/`rich`는 UI가 Unit B(opencode)로 빠져 불필요)

## 1. 성능/용량
- 단일 운영자, 저빈도 명령. file-drop 폴링 1–2s(C-3 snapshot publisher는 별도 주기). 처리량 이슈 없음 — 단일 CommandWorker로 충분.
- 응급 명령 지연은 "즉시" 아님: worst-case ~11s(BR-13, broker 호출 선점 불가). NFR로 이 상한을 **명시적 수용**.

## 2. 동시성 (상세는 NFR Design)
- 단일 CommandWorker(broker 변이+executor 커서) + 단일 turn_lock(LLM 세션). 스케줄러 executor 호출도 워커로 funnel(BR-7.1').
- `TurnCoordinator`/`turn_lock`/`ReconcileWorker`는 **신규 구현**(main 부재). 스케줄러 `max_instances=1, coalesce=True` 명시.

## 3. 신뢰성/fault isolation
- 스레드 격리 + best-effort + fail-closed(BR-6.3/BR-8). 운영자 도구 부재/크래시에도 데몬 정상.
- file-drop torn-safe 바이트오프셋 리더 + id-dedup(BR-11). 원자적 쓰기(snapshot/cursor: temp+`os.replace`, stdlib).

## 4. 보안 (Security Baseline enforced, Q9=A)
- **SECURITY-11(핵심):** 권한 분리(BR-10). **BR-10.1 PreToolUse 훅**(에이전트=claude 측)이 1차 구조 경계 — 기술적 실현은
  Claude Code 훅(settings.json + 결정적 거부 스크립트), opencode 무관(§tech-stack). 토큰 out-of-band(BR-10.2).
- **SECURITY-03:** 토큰/비밀 비기록. **SECURITY-13:** pydantic 안전 역직렬화 + append-only. **SECURITY-15:** fail-closed 전반.
- **SECURITY-10:** Unit A는 신규 런타임 의존성이 없어 신규 핀 불필요(있다면 핀). (opencode/Unit B 측 의존성 핀은 Unit B NFR에서.)

## 5. 테스트/PBT (Partial, Hypothesis — 이미 dev 의존성)
- PBT-02/03(레코드 round-trip, 파서/검증/락-상태머신/커서 단조/토큰 검증 불변식). example로 안전경로+권한거부 고정.
- **신규 검증 항목:** (a) PreToolUse 훅이 `workspace/` 밖 접근을 거부, 에이전트 env에 토큰 부재; (b) `claude -p` 헤드리스에서
  훅 로딩 위치(`workspace/.claude/settings.json` 등) 실측.

## 6. 신규 질문 없음
모든 tech-stack 결정이 기설정값(0 신규 런타임 deps, stdlib, Hypothesis dev) + 앞선 답변(Q3=A 폴링, BR-10 훅/토큰)으로
귀결됨. NFR Design으로 이월: 직렬화 primitive 구현(Lock vs 큐 워커), 훅 스크립트 형태/위치, snapshot publisher 주기.
