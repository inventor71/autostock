# F14 요구사항 — 데몬 wedge 자가복구 + 마켓데이터 fetch 경직성 수정

> 깊이: **Standard** (신뢰성 버그픽스 + 소규모 기능). brownfield, 기존 RE 아티팩트 활용.
> 미결정 사항은 `questions.md` 참조 — 답변 확정 후 본 문서를 갱신한다.

## 1. 목적
단일 데몬 프로세스가 살아있는(systemd `active`) 상태에서도 `steering/snapshot.json`의
`published_at`이 정지하는 **wedge** 현상을 (1) 발생 가능성 자체를 줄이고, (2) 발생 시
자동으로 복구하여, 운영자가 수동 `systemctl restart` 없이 `autostock` 콘솔에 다시 붙을 수
있도록 한다.

## 2. 기능 요구사항 (FR)

### A. broker/데이터 HTTP 타임아웃 (근본 방어)
- **FR-A1** `AlpacaBroker`(src/execution/brokers/alpaca_broker.py)가 사용하는 Alpaca 클라이언트의
  모든 네트워크 호출에 connect + read 타임아웃이 적용되어야 한다.
- **FR-A2** Alpaca 데이터 provider(src/data/providers/alpaca_provider.py)의 가격/바 조회에도
  동일하게 타임아웃이 적용되어야 한다.
- **FR-A3** 타임아웃 초과는 **예외로 raise**되어, 기존 best-effort `try/except`(BarCache,
  publish_snapshot `_build`)가 잡고 다음 tick에 재시도/캐시폴백으로 자가복구되어야 한다.
- **AC-A** 네트워크가 half-open으로 멈춘 상황을 모사해도 한 tick이 (타임아웃 + α) 내에 종료되며,
  워커/스케줄러 스레드가 영구 블록되지 않는다.

### B. WakeDetector 동기 fetch 경직성 완화
- **FR-B1** `detect_wakes`(5초 주기)는 스케줄러 스레드에서 **동기 마켓데이터 fetch를 하지 않아야**
  한다. (`bars.py` docstring이 명시한 불변식을 실제로 보장.)
- **FR-B2** 현재 `BarCache.price_ttl(~3초)`가 5초 루프와 충돌해 사실상 매 tick HTTP를 치는 문제를
  해소한다. (TTL 조정 또는 prefetch 분리 — `questions.md` Q-B 참조.)
- **AC-B** 정상 운영 시 `detect_wakes` 한 tick은 캐시 읽기만으로 ms 단위에 끝나며,
  `skipped: maximum number of running instances` 경고가 정상 상태에서 발생하지 않는다.

### C. 런처 self-heal (active + published_at 정지 시 1회 복구)
- **FR-C1** `autostock` 실행 시 데몬 unit이 `active`이지만 `published_at`이 patience 윈도 동안
  advance 0회이면 **wedge로 판정**한다. (윈도 값 — `questions.md` Q-C1.)
- **FR-C2** wedge 판정 시 `systemctl --user restart`를 **자동 1회** 수행한 뒤 health-wait로
  advance를 재확인한다. (재시작/대기 정책 — Q-C2, Q-C3.)
- **FR-C3** 복구 성공 시 attach, 실패 시 운영자에게 **명확한 진단 메시지**(저널 명령 포함)를 보고한다.
- **FR-C4** 정상적인 장시간 LLM 턴(프리마켓 리서치/인트라데이)은 중간에 advance가 관측되므로
  **절대 wedge로 오판해 죽이지 않는다**. (오탐 방지가 최우선 제약.)
- **AC-C** active+정지 상태를 모사하면 1회 자동 restart 후 attach 성공. 정상 긴 턴(advance 간헐적
  관측)에서는 restart가 트리거되지 않음.

## 3. 비기능 요구사항 (NFR)
- **NFR-1 안전 우선**: self-heal은 라이브 데몬을 같은 broker로 이중 기동하면 안 된다. restart는
  systemd 단위 재시작(기존 프로세스 종료 보장)으로만.
- **NFR-2 단일 writer 보존**: broker 변경 경로(CommandBus 단일 워커, NFR-2)는 유지. 이번 수정은
  타임아웃/캐시/런처 계층에 한정.
- **NFR-3 best-effort**: 데이터 fetch 실패가 스냅샷 발행/스케줄러를 죽이면 안 된다(기존 원칙 유지).
- **NFR-4 회귀 방지**: 기존 launcher.test.ts의 freshness/advance 시맨틱과 충돌하지 않게.

## 4. 스코프 밖
- 장기 백그라운드 watchdog(점진 백오프 5분→…→4시간 상한). 후속 트랙 후보.
- broker 호출의 전면 비동기화/오프-워커 재설계.
- broker SDK 교체.

## 5. 확정 결정 (2026-05-31 사용자 답변 — questions.md)
| 질문 | 답 | 확정 내용 |
|------|----|-----------|
| Q-SCOPE | A | **A+B+C 전부** 이번 F14에 포함 |
| Q-A1 | A | HTTP 타임아웃 **connect 3s / read 5s** (공격적, 빠른 자가복구) |
| Q-A2 | A | alpaca-py SDK 노출 타임아웃 파라미터 사용 — **⚠️ 단서 아래** |
| Q-B1 | B | detect_wakes 동기 fetch를 **별도 prefetch 워커**로 분리(detect는 캐시만 read) |
| Q-B2 | A | prefetch 주기 **가격 5s / 바 60s**(현 bars_ttl 유지) |
| Q-C1 | A | wedge 판정 patience 윈도 **3분** (advance 0회 지속 시) |
| Q-C2 | A | restart 후 health-wait **60s**(기존 HEALTHWAIT_TIMEOUT_MS 재사용) |
| Q-C3 | A | 인터랙티브 1회 실행당 **자동 restart 1회**, 실패 시 진단 메시지 보고 |
| Q-C4 | A | self-heal을 **`DaemonService.ensureRunning` 안에 wedge 분기**로 추가 |
| Q-SEC | A | **Security Baseline 적용**(enforce) — §6 참조 |
| Q-VERIFY | A | py-spy 환경 설치 + 재발 시 `py-spy dump --pid` 캡처 |

### ⚠️ Q-A2 설계 단서 (NFR Design에서 검증 필요, 비차단)
현재 코드(`alpaca_broker.py:72`)는 `TradingClient(api_key, secret_key, paper=paper)`로
생성하며 **타임아웃 인자를 주지 않는다.** alpaca-py의 `TradingClient`/데이터 클라이언트가
connect/read 타임아웃 파라미터를 **실제로 노출하는지는 SDK 버전 의존**이다(노출 안 할 가능성 큼).
→ Q-A2=A의 운영 규칙: "SDK 파라미터가 있으면 그것 사용, **없으면 하부 HTTP 세션/httpx 레벨에서
강제 주입(Q-A2의 B로 폴백)**". 어느 경로든 connect 3s/read 5s가 **모든** 네트워크 호출에 실제
적용되는지(FR-A1/A2/AC-A)가 수용 기준이다. NFR Design에서 alpaca-py 버전 확인 후 확정.

### Q-C1 비고
권장값은 5분이었으나 사용자가 **3분**을 선택(빠른 복구 우선). 정상 인트라데이/리서치 턴은
중간에 advance가 관측되므로 3분 무(無)advance면 wedge로 보아도 오탐 위험은 낮다(FR-C4 불변식과
양립). 단, **프리마켓 콜드스타트 리서치 배치가 3분 넘게 단일 호출로 advance 없이 지속될 여지**가
있는지는 Application/NFR Design에서 점검(필요 시 최초 기동 직후 grace 예외).

## 6. 보안 컴플라이언스 (Security Baseline, Q-SEC=A)
적용 대상 룰(이 트랙 관련만):
- **SECURITY-03 (앱 로깅 / 시크릿 미로깅)**: self-heal·타임아웃 경로의 새 로그가 토큰
  (`STEERING_OPERATOR_TOKEN`)·API 키를 출력하지 않을 것. restart 진단 메시지에 시크릿 비포함.
- **SECURITY-11 (보안 설계 / defense-in-depth)**: 타임아웃은 단일 방어가 아니라 계층(타임아웃 +
  best-effort try/except + 런처 self-heal)으로. self-heal은 라이브 데몬 이중기동 금지(NFR-1).
- **SECURITY-15 (예외 처리 / fail-closed)**: 모든 외부 호출(broker/데이터 HTTP, systemctl)에
  명시적 에러 처리. 타임아웃 raise는 잡아 다음 tick 재시도(자가복구), self-heal restart 실패 시
  **fail-closed로 명확히 실패 보고**(거짓 attach 금지). 리소스(소켓) 정리.
- **SECURITY-06/10/12/13/14** 등 기타: **N/A**(웹/DB/IaC/사용자 인증/배포 파이프라인 신규 없음;
  의존성 신규 추가 없음 — 기존 alpaca-py 재사용).

## 7. 미결정 (→ /ai-dlc-resume 의 Workflow Planning / Design 에서)
- alpaca-py 타임아웃 노출 여부 실측 → Q-A2 경로 확정(§5 ⚠️).
- prefetch 워커 실행 위치(별도 스레드 vs 기존 스케줄러 seconds job)와 심볼 소스(snapshot의
  held+watched). Q-B2=A 주기 적용. **CommandBus 단일 워커에 얹지 않을 것**(NFR-2 — 데이터 fetch는
  read-only이므로 분리 가능).
- C1 콜드스타트 grace 예외 필요 여부.
- 단위 분할: A/B/C를 1개 unit으로 갈지 3개 작은 unit으로 갈지(Units Generation).
