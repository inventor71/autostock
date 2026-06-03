# Functional Design Plan — KisBroker / KisDataProvider (F30)

> Unit: `kis-broker` (KisBroker + KisDataProvider + executor/scheduler 수정).
> 단계: CONSTRUCTION → Functional Design. Application Design 승인 완료 기반.
> 산출물 예정: `aidlc-docs/construction/kis-broker/functional-design/{business-logic-model,business-rules,domain-entities}.md`
>
> **작성 정책**: 설계 문서이므로 main 루트에서 작성. 실제 코드(src/)는 worktree(`feat/F30`)에서만.

## 목적
Application Design에서 확정한 컴포넌트 구조(KisBroker capability, Option B emulated bracket/OCO,
서킷브레이커/스케줄러 broker-aware) 위에, **기술 비종속 비즈니스 로직**을 상세화한다:
주문유형 매핑·호가단위 반올림·정수 수량·토큰 수명·emulated OCO reconcile·universe·KST 장 시간.

## 실행 체크리스트
> U1=kis-broker, U2=universe-provider. 산출물: `construction/{kis-broker,universe-provider}/functional-design/`
- [x] **FD-1** 주문유형 매핑 규칙 확정 → U1 business-rules BR-1
- [x] **FD-2** 호가단위(tick) 반올림 규칙(Q2=A nearest) → U1 BR-2
- [x] **FD-3** 정수 수량 변환 규칙(Q3=A) → U1 BR-3
- [x] **FD-4** emulated bracket/OCO 상태기계(Q1=A, Q4=A) → U1 business-logic §3, BR-5
- [x] **FD-5** 토큰 수명 관리(Q5=A lazy) → U1 §2, BR-4
- [x] **FD-6** KST 장 시간 / 스케줄 → U1 §4, BR-6
- [x] **FD-7** universe 정의(Q6=B → 별도 unit U2) → U2 전체 (KR=ETF 구성종목, US=S&P100 동적, 테마 overlay)
- [x] **FD-8** standalone 가격 피드 범위(Q7=A) → U1 §5
- [x] **FD-9** close_position 청산 전략(Q8=A 시장가) → U1 §7, BR-7
- [x] **FD-10** 에러 처리 / fail-closed → U1 BR-9, U2 UR-6
- [x] **FD-11** 도메인 엔티티 매핑표 → U1 domain-entities, U2 domain-entities
- [x] **FD-12** PBT 대상 식별 → U1 BR §PBT, U2 UR-7
- [x] FD 산출물 6종(2 units × 3) 작성 + 완료 메시지(2-option) 제시

---

## 명확화 질문 (답변 후 진행)

> 답변은 각 `[Answer]:` 뒤에 기입해 주세요. (형식: 보기 선택 `A`/`B`/… 또는 자유 서술)
> 애매한 답("상황에 따라" 등)은 추가 질문으로 되묻습니다.

### Q1. emulated OCO 한쪽 체결 시 다른 쪽 취소 — 폴링 주기
KIS는 네이티브 OCO 자동취소가 없어 `reconcile_oco()` 폴링으로 재현합니다.
- **A.** 기존 5초 intraday job에 `reconcile_oco`를 함께 태운다 (추가 스레드 없음, 최대 5초 지연) — 권장
- **B.** 더 촘촘한 별도 주기(예: 2초) — 빠른 정합성, rate-limit 부담↑
- **C.** 기타(서술)

[Answer]: A

### Q2. 호가단위(tick) 반올림 방향
지정가/스탑지정가 가격을 KOSPI/KOSDAQ tick(가격대별 1/5/10/50/100/500/1000원)으로 맞춥니다.
방향 정책:
- **A.** 모두 **최근접(nearest)** tick 반올림 — 단순/대칭 — 권장
- **B.** 체결 보수적: BUY LIMIT/TP는 내림(floor), SELL LIMIT/스탑지정가는 올림(ceil) — 의도와 어긋난 즉시 불리체결 방지
- **C.** 기타(서술)

[Answer]: A

### Q3. 정수 수량 변환 정책
KIS 국내주식은 정수 수량만 가능(소수주 불가):
- **A.** BUY/부분 SELL = **내림(floor)**, **전량 청산은 보유수량 그대로**(floor 무관), resting TP/SL leg 수량 = 진입 체결수량 — 권장
- **B.** 모든 경로 floor (전량 청산도 보유수량 floor — 정수면 동일)
- **C.** 기타(서술)

[Answer]: A

### Q4. emulated bracket 진입 체결 확인 시점
BRACKET 주문(진입+TP+SL)에서 TP/SL resting leg는 진입 체결 수량/가격이 정해져야 걸 수 있습니다.
- **A.** 진입 주문 직후 **동기 폴링**으로 체결 확인(짧은 타임아웃) → 즉시 TP/SL arm. 미체결이면 다음 reconcile 턴에서 arm — 권장
- **B.** 진입만 제출하고 TP/SL arm은 **항상 다음 reconcile 턴**으로 위임(논블로킹, 보호 지연 가능)
- **C.** 기타(서술)

[Answer]: A

### Q5. KIS 액세스 토큰(24h 만료) 갱신 전략
- **A.** **Lazy** — 매 API 호출 전 토큰 나이 체크, >23h이면 재발급 (스레드 없음, 단순) — 권장
- **B.** 백그라운드 23h 주기 갱신 스레드
- **C.** 기타(서술)
 
[Answer]: A

### Q6. universe(KOSPI200 + KOSDAQ150) 종목 소스
- **A.** repo 내 **정적 종목 리스트 파일**(config) — 결정적/오프라인, 분기 수동 갱신 — 권장(PoC)
- **B.** KIS API로 지수구성종목 동적 조회 — 최신성↑, API 의존/rate-limit
- **C.** 기타(서술)

[Answer]: B. 현재 미주는 universe 종목 소스가 동적으로 업데이트 되나? 만약 안되어있다면 이건 따로 unit으로 해서 이번 F30에서 처리해줘.

### Q7. standalone 가격 피드 / reconcile job 폴링 대상
steering 없이 KIS 단독 실행 시(기존 5초 job이 `if self.steering` 블록 안이라 미동작) 최소 폴링:
- **A.** **보유 포지션 + open order 심볼만** 현재가 폴링(+reconcile_oco) — rate-limit 절약, 보호에 충분 — 권장
- **B.** universe 전체(≈350) 폴링 — 모니터링 풍부, rate-limit 부담 큼
- **C.** 기타(서술)

[Answer]: A

### Q8. close_position / 강제 청산 가격 전략
- **A.** **시장가(ORD_DVSN=01) 매도** — 확실한 청산(슬리피지 감수) — 권장
- **B.** 현재가 bid 기준 **지정가** 매도 — 가격통제(미체결 가능)
- **C.** 기타(서술)

[Answer]: A

---

## 다음 액션
위 8개 질문 답변 → 분석/추가질문(필요시) → FD 산출물 3종 작성 → 2-option 완료 게이트.
실제 코드 생성은 그 다음 Code Generation 단계에서 `feat/F30` worktree에서 수행.
