# 비즈니스 규칙 — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · Functional Design · 2026-05-29._

결정 규칙·검증·제약. 각 규칙은 코드 생성/테스트로 강제된다. (Security/PBT 매핑 포함.)

---

## BR-1 확인(confirm) 규칙
- BR-1.1 모든 거래(`/buy /sell /flatten /stop`)·lifecycle(`/pause /resume /halt-entries /allow-entries`)·
  `/cancel`은 해석을 에코한 뒤 `[y/N]`(기본 N)으로 실행. 빈 입력/`n`/타임아웃 → **no-op**(fail-closed, SECURITY-15).
- BR-1.2 파괴적 명령(`/flatten all`, `/kill`)은 `CONFIRM` 키워드 재입력을 요구(CQ4-b=A). 불일치 → no-op.
- BR-1.3 읽기 명령(`/status /positions /orders /log /help /pending /directives`)과 `/note`,`/directive`는 확인 없음.
- BR-1.4 확인 프롬프트 출력 중에는 다른 입력을 받지 않는다(확인은 동기). 단 승인 알림(BR-5)은 블로킹하지 않는다.

## BR-2 거래 실행 규칙 (사람 강제 거래)
- BR-2.1 사람 거래는 반드시 `DecisionExecutor`→`RiskManager`(bracket/OCO)→`Broker`의 **동일 게이트**를 통과한다.
  별도 주문 경로를 만들지 않는다(Q6=A). 결과 protection은 에이전트 거래와 동일하게 적용.
- BR-2.2 `Decision.source="human"`으로 태깅(E1).
- BR-2.3 크기 의미: `$`=노셔널, `sh`=주식 수, `%`=보유 비율(매도 전용). RiskManager가 한도/리스크로 추가 제약 가능.
- BR-2.4 시장 폐장 등으로 즉시 체결 불가 시 기존 executor 정책을 따른다(보류/연기). 결과는 `InterventionRecord`에 반영.
- BR-2.5 `/buy`,`/sell`,`/flatten`은 대상 종목에 **HumanLock 생성**(BR-4). `/stop`은 락 생성 안 함.

## BR-3 게이팅 규칙 (RunState)
- BR-3.1 `paused=True`: 예약 리서치/intraday/진입 턴은 no-op. **보호·resting 체결·`run_risk_exits` 청산은 계속**(Q9=A, 안전).
  사람 명령은 paused 중에도 동작.
- BR-3.2 `entries_halted=True`: 에이전트 신규 BUY 실행 차단. 기존 포지션 관리/청산/보호 유지. 사람 `/buy`는 경고 후 실행(오버라이드).
- BR-3.3 `RunState`는 영속하지 않는다 — 데몬 재시작 시 `running`, 진입 허용으로 시작(Q9=A).

## BR-4 사람-락 상태머신 (E4) — 핵심 일관성 규칙
- BR-4.1 사람의 `/buy|/sell|/flatten <SYM>` 성공 시 그 종목은 `locked(reject_count=0)`.
- BR-4.2 종목이 `locked`이고 에이전트가 **재량 거래(BUY/SELL)** 결정을 내면: 실행하지 않고 `PendingApproval` 생성 + 콘솔 알림.
- BR-4.3 `/approve` → 결정 실행(게이트) + **락 해제**(CQ1 노트: "한번 허용하면 락 풀림"). 이후 사람이 다시 손대면 재-락 가능.
- BR-4.4 `/reject` → 미실행, `reject_count += 1`. `reject_count==1`이면 `locked` 유지(에이전트 재요청 가능),
  `reject_count==2`이면 `denied`(당일 영구 거부).
- BR-4.5 종목이 `denied`이고 에이전트가 재량 거래 결정을 내면: **자동 거부**(PendingApproval 미생성) + 에이전트 피드백.
- BR-4.6 **락 예외(항상 자율 실행):** 에이전트의 보호주문 — 미보호 포지션 OCO/스탑 등록, 기존 OCO 수정, `ADJUST_STOP`,
  `HOLD`+stop. 불변식 "모든 포지션은 보호되어야 함"을 깨지 않기 위함.
- BR-4.7 `/unlock <SYM>`은 `locked`/`denied`를 즉시 해제(reject_count 리셋).
- BR-4.8 모든 락/카운트/denied/pending은 **ET 날짜 스코프** — 다음 거래일 자동 해제. 같은 날 재시작은 영속 파일에서 복원.
- BR-4.9 **불변식(PBT-03):** `reject_count`는 0→1→2 단조 증가; `status=="denied" ⇔ reject_count>=2`; `/approve`/`/unlock` 후 종목은 락 집합에서 제거.

## BR-5 승인 대기 노출/처리 (CQ2=A)
- BR-5.1 `PendingApproval` 생성 시 콘솔에 **한 줄 알림**(non-blocking) 출력 + `/status` 카운트 반영.
- BR-5.2 `/pending`으로 목록, `/approve <id>` / `/reject <id> [사유]`로 처리. 알 수 없는 id → 거부+사유.
- BR-5.3 처리 결과(승인/거부/denied)는 **에이전트 피드백**으로 기록(저널/프롬프트 노출) — 무한 재시도 방지(Q8 노트).

## BR-6 reconcile(재정렬) 규칙
- BR-6.1 트리거: 사람 거래, `/directive` 등록, approve/reject로 장부 변경 직후. `/note`·읽기 명령은 트리거 안 함(Q7=A).
- BR-6.2 비동기 실행, 예약 턴과 **turn-lock 공유**(동시 LLM 세션 금지). 다수 개입은 디바운스로 1회 합침.
- BR-6.3 **best-effort**: reconcile 실패(타임아웃 등)는 로그만 남기고 데몬을 중단시키지 않는다(SECURITY-15, 기존 `_launch` 정책).

## BR-7 동시성/직렬화 (요지 — 상세 NFR Design)
- BR-7.1 콘솔 변이 명령, 스케줄러 잡, reconcile 턴은 **단일 직렬화 경로**(락/큐)를 통과한다 — 브로커/executor 커서/
  CLI 세션 레이스 방지(NFR-1).
- BR-7.2 읽기 명령은 직렬화 경로 없이 조회 가능(부수효과 없음).

## BR-8 에러/안전 규칙 (fail-closed, SECURITY-15)
- BR-8.1 파싱/검증 실패는 부분 실행 없이 사유만 출력.
- BR-8.2 콘솔 스레드의 어떤 예외도 데몬을 죽이지 않는다(스레드 격리, try/except, 락은 finally 해제).
- BR-8.3 비-TTY(분리 실행) 감지 시 콘솔 자동 비활성화 + 한 줄 공지, 데몬은 정상 거래.
- BR-8.4 `/cancel`이 보호주문을 제거할 경우 경고. (폴드 청산 백업 `run_risk_exits`는 여전히 안전망.)

## BR-9 로깅/감사 규칙 (SECURITY-03/13)
- BR-9.1 모든 개입은 `InterventionRecord`로 append-only 기록(누가=사람, 무엇, 언제, 결과 — 감사 가능, SECURITY-13).
- BR-9.2 로그/콘솔 출력에 비밀정보(API 키 등) 미포함(SECURITY-03). 종목/수량/가격/사용자 텍스트만.
- BR-9.3 콘솔 부착 중 loguru stdout 끔(파일 싱크 유지) — `/log`로 엿보기(Q3=A).

---

## 컴플라이언스 매핑 (이 단계 기준)
- **SECURITY-03**: BR-9.2/9.3. **SECURITY-11**: 스티어링 로직과 주문배치 분리(executor/RiskManager 재사용),
  방어심층(사람의도+게이트+확인), 오남용 케이스(`/flatten all`·`/kill` 강확인) — BR-1.2/2.1/7.
  **SECURITY-13**: BR-9.1(감사 가능, append-only), pydantic 안전 역직렬화(E2/E5). **SECURITY-15**: BR-8 전반/BR-6.3.
- **PBT-03(불변식)**: BR-4.9(락 상태머신), BR-2.2/파서(BR-2.3). **PBT-02(라운드트립)**: E2/E5 직렬화.
  **PBT-10(보완)**: 예제 테스트로 강확인 흐름·kill·paused 스킵·게이팅·보호 예외·reconcile 실패 내성 고정.
