# 콘솔 UX (프런트엔드) — human-steering-console

_AI-DLC 트랙 F2 · CONSTRUCTION · Functional Design · 2026-05-29._

콘솔이 이 기능의 UI다. 화면/상호작용/출력 형식을 정의한다. (요구사항: 신규 런타임 의존성 0 — Python stdlib만.)

---

## C1. 실행/런치 모델 (CQ5=A)
- Q1=B(인-프로세스 REPL)이므로 **콘솔 = 데몬**. `main.py --mode agent`가 스케줄러 스레드와 함께
  전용 스레드에서 REPL을 띄운다.
- `scripts/monitor.sh`에 패널을 하나 추가/지정하여 거기서 `main.py --mode agent`(REPL 포함)를 실행한다.
  나머지 패널은 지금처럼 파일 tail(decisions/turns+trades/status/log). 입력 패널 = 콘솔.
- tmux 패널이므로 항상 TTY + detach/attach 가능(분리 실행 시 TTY 없음 → 콘솔 자동 비활성화, BR-8.3).
- 제안 레이아웃(기존 4패널 + 콘솔):
```
+------------------+---------------------------+
| decisions (live) | account dashboard (status)|
+------------------+---------------------------+
| turns + trades   | agent log (autostock.log) |
+------------------+---------------------------+
| >>> CONSOLE (main.py --mode agent, REPL) <<< |
+----------------------------------------------+
```

## C2. 프롬프트
- 기본: `autostock> `
- 상태 표시: `autostock[running]> ` / `autostock[PAUSED]> ` / `autostock[halt-entries]> `
- 승인 대기 존재 시 접미: `autostock[running ⚠2]> ` (대기 2건).

## C3. 시작 배너 (콘솔 부착 시)
```
autostock 휴먼 스티어링 콘솔 — paper=<true|false> · 종목 <N>개
상태: running · 보유 <N> · 승인대기 0
'/help' 로 명령 보기. 로그는 'agent log' 패널 또는 '/log' 로.
autostock[running]>
```
- 비-TTY면 배너 대신 로그에 한 줄: `console disabled (no TTY); daemon trading normally`.

## C4. 명령 실행 후 피드백 (Q4=A — 해석 + 한 줄 결과)
- 거래 성공: `✓ SELL 100% AAPL — 12sh @ $190.20 체결 (order abc123)`
- 거래 무주문: `· SELL AAPL — 주문 없음 (RiskManager: <사유>)`
- 거래 실패: `✗ BUY AAPL — 실패: <사유>`
- lifecycle: `✓ 일시정지됨 (신규 리서치/진입 중단; 보호·청산은 계속)`
- 보호: `✓ STOP AAPL → $185.00 설정`
- 취소: `✓ AAPL 미체결 주문 2건 취소` / 경고 동반: `⚠ 보호주문이 제거됩니다 — 폴드 청산 백업만 남음`

## C5. 확인 플로우
- 일반(BR-1.1):
```
autostock[running]> /sell AAPL 50%
해석: SELL 50% AAPL @ 시장가 (보유 24sh 중 12sh)
실행할까요? [y/N]: y
✓ SELL 50% AAPL — 12sh @ $190.20 체결 (order abc123)
```
- 강확인(BR-1.2 — `/flatten all`, `/kill`):
```
autostock[running]> /flatten all
⚠ 전 종목 청산 + 전체 미체결 취소: 5개 포지션 · 8개 주문.
실행하려면 'CONFIRM' 입력: CONFIRM
✓ 5개 포지션 청산 요청 · 8개 주문 취소
```
- 거부/타임아웃 → `· 취소됨` (no-op).

## C6. 승인 대기 (CQ2=A — 알림 줄 + 명령형)
- 대기 발생 시 비블로킹 한 줄:
```
⚠ 승인 대기 #3: 에이전트 BUY AAPL ~$5,000 (stop 182 / tgt 205) — /approve 3 | /reject 3
```
- `/pending`:
```
autostock[running ⚠2]> /pending
#2  에이전트 SELL 100% TSLA   사유: "모멘텀 붕괴"        대기 4분
#3  에이전트 BUY AAPL ~$5,000  사유: "되돌림 진입"        대기 1분
'/approve <id>' 또는 '/reject <id> [사유]'
```
- 처리:
```
autostock[running ⚠2]> /reject 3 아직 하락 추세
✓ #3 거부 — AAPL 락 유지(거부 1/2). 에이전트에 통보됨.
autostock[running ⚠1]> /approve 2
✓ #2 승인 — SELL 100% TSLA 18sh @ $242.10 체결. TSLA 락 해제.
```

## C7. 맥락/스티어링
```
autostock[running]> /note 오늘 CPI 발표, 변동성 주의
✓ 노트 기록 (다음 예약 턴에 반영)
autostock[running]> /directive 이번 주 신규 기술주 진입 금지
✓ 지시 #1 등록 (상시; 에이전트 재정렬 트리거)
autostock[running]> /directives
#1  이번 주 신규 기술주 진입 금지   (등록 09:32)
autostock[running]> /directive clear 1
✓ 지시 #1 해제
```

## C8. 읽기 명령 출력 예
- `/status`:
```
상태: running · paused=False · halt_entries=False
보유 5 · 미체결 8 · 승인대기 2 · 락 종목: AAPL(locked) NVDA(denied 2/2)
마지막 턴: intraday 10:15 · 다음 intraday ~10:30
```
- `/positions` (= `/book`): 종목·수량·평단·현재가·미실현손익·보호(스탑/타겟) 한 줄씩.
- `/orders`: 종목·side·type·수량·가격·상태 한 줄씩.
- `/log [n]`: 최근 n줄(기본 20) `logs/autostock.log` 출력.

## C9. 도움말 (`/help`) — 그룹별
```
거래   /buy SYM <N$|Nsh> · /sell SYM <N%|Nsh|N$> · /flatten SYM · /flatten all · /stop SYM <price>
운영   /pause · /resume · /halt-entries · /allow-entries · /kill
승인   /pending · /approve <id> · /reject <id> [사유] · /unlock SYM
맥락   /note <text> · /directive <text> · /directives · /directive clear [id|all]
조회   /status · /positions(/book) · /orders · /cancel SYM · /log [n] · /help [cmd]
```
- `/help <cmd>` → 해당 명령 인자/예시/확인 여부 상세.

## C10. 에러 메시지 (한국어, fail-closed)
| 상황 | 메시지 |
|---|---|
| 비-슬래시 입력 | `알 수 없는 입력입니다. '/help' 를 참고하세요.` |
| 미등록 명령 | `알 수 없는 명령: /xyz — '/help' 참고` |
| 크기 단위 누락/오류 | `크기 단위가 필요합니다: $ 또는 sh — 예) /buy AAPL 1000$ | /buy AAPL 5sh` |
| 매도 단위 누락 | `매도 크기를 명시하세요: % / sh / $ — 예) /sell AAPL 50%` |
| 보유 없음에 매도/flatten | `AAPL 보유 포지션이 없습니다.` |
| 잘못된 승인 id | `승인 대기 #9 가 없습니다. '/pending' 확인.` |

## C11. 로그/프롬프트 분리 (Q3=A)
- 콘솔 부착 시 loguru의 **stdout 싱크 제거**, 파일 싱크(`logs/autostock.log`) 유지 → 프롬프트가 로그에 안 묻힘.
- 로그 확인은 monitor.sh의 'agent log' 패널 또는 `/log`.

---

## 식별된 테스트 가능 속성 (PBT-01, 이 컴포넌트)
- **파서 불변식(PBT-03)**: 모든 유효 `/buy`,`/sell` 입력 → 단위 규칙을 지키는 명령 산출; 단위 없거나 잘못되면
  항상 거부(실행 가능 형태 미산출); `%`는 (0,1] frac.
- **라운드트립(PBT-02)**: `InterventionRecord`/`PendingApproval` 직렬화→역직렬화 == 원본.
- **예제(PBT-10)**: 강확인 흐름(CONFIRM), 거부/타임아웃 no-op, 승인 알림·`/pending` 표시, 에러 메시지 매핑.
